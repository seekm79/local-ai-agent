"""All LLM access funnels through here (Global rule 9).

Provides the live model list plus streaming chat with per-call model selection,
sampling, and thinking-mode support. Qwen3.6 emits reasoning; we separate it
from ordinary content two ways for maximum compatibility:

  1. If Ollama's OpenAI-compatible endpoint returns a `reasoning`/
     `reasoning_content` delta field (recent Ollama with `think` enabled), we
     stream it as reasoning.
  2. Otherwise we parse inline ``<think>...</think>`` tags out of the content
     stream with a boundary-safe splitter, so models that inline their thinking
     still render collapsed.

Locked stack: the actual generation goes through the `openai` async client
pointed at Ollama's `/v1` with a dummy key.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import AsyncIterator, Literal

import httpx
from openai import AsyncOpenAI

from .. import config

# OpenAI-compatible client against Ollama. api_key is a dummy Ollama ignores.
_client = AsyncOpenAI(base_url=config.OLLAMA_BASE_URL, api_key=config.OLLAMA_API_KEY)

_MODELS_URL = f"{config.OLLAMA_BASE_URL.rstrip('/')}/models"

# Event kinds yielded by stream_chat.
Kind = Literal["reasoning_delta", "delta"]


async def list_models() -> list[str]:
    """Return model ids from Ollama's `GET /v1/models`. Raises on failure so the
    caller can surface the real error (Global rule 7 — no silent failures)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_MODELS_URL)
        resp.raise_for_status()
        data = resp.json()
    return [m["id"] for m in data.get("data", [])]


_VISION_HINTS = ("vl", "llava", "vision", "minicpm-v", "moondream", "bakllava")


async def find_vision_model() -> str | None:
    """Pick an installed multimodal model (env override wins, else name hints)."""
    override = os.environ.get("WORKBENCH_MODEL_VISION")
    try:
        models = await list_models()
    except Exception:
        return None
    if override and override in models:
        return override
    for m in models:
        base_name = m.lower().split(":")[0]
        if any(h in base_name.split("-") for h in _VISION_HINTS) or \
                any(h in m.lower() for h in ("llava", "vision", "moondream")):
            return m
    return None


async def describe_image(path: str | Path, purpose: str = "design reference") -> str | None:
    """Describe an image with an installed vision model. Uses Ollama's NATIVE
    /api/chat (not the OpenAI shim) so we can force a small num_ctx — large
    vision models default to huge contexts (qwen3-vl: 262k ≈ 89 GB, spilling to
    CPU and taking minutes); at 8k it fits on GPU and answers in seconds.
    Returns None when no vision model exists or the call fails — attachment
    flows must keep working without one."""
    model = await find_vision_model()
    if model is None:
        return None
    native = config.OLLAMA_BASE_URL.rstrip("/").removesuffix("/v1")
    try:
        b64 = base64.b64encode(Path(path).read_bytes()).decode()
        async with httpx.AsyncClient(timeout=240.0) as client:
            resp = await client.post(f"{native}/api/chat", json={
                "model": model,
                "stream": False,
                "keep_alive": "30s",
                # thinking burns the whole token budget before any answer on
                # reasoning VL models (qwen3-vl) — disable it for descriptions.
                "think": False,
                "options": {"num_ctx": 8192, "num_predict": 400},
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Describe this image as a {purpose} for a web-app builder: "
                        "subject, layout, style, mood, dominant colors, typography "
                        "if any. 3-5 sentences, concrete and specific."),
                    "images": [b64],
                }],
            })
            resp.raise_for_status()
            msg = resp.json().get("message") or {}
            content = msg.get("content", "")
        return content.strip() or None
    except Exception:
        return None


def _max_suffix_prefix(s: str, marker: str) -> int:
    """Largest k (< len(marker)) such that `s` ends with `marker[:k]`.

    Used to hold back a trailing partial tag that might complete on the next
    chunk (e.g. text ending in "<thi")."""
    maxk = min(len(s), len(marker) - 1)
    for k in range(maxk, 0, -1):
        if s.endswith(marker[:k]):
            return k
    return 0


class ThinkSplitter:
    """Boundary-safe splitter for inline ``<think>...</think>`` tags.

    Feed content chunks; get back a list of ``(kind, text)`` where kind is
    "reasoning_delta" (inside think tags) or "delta" (normal content). Partial
    tags spanning chunk boundaries are buffered until resolved."""

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, text: str) -> list[tuple[Kind, str]]:
        self._buf += text
        out: list[tuple[Kind, str]] = []
        while True:
            marker = self.CLOSE if self._in_think else self.OPEN
            idx = self._buf.find(marker)
            if idx != -1:
                before = self._buf[:idx]
                if before:
                    out.append(
                        ("reasoning_delta" if self._in_think else "delta", before)
                    )
                self._buf = self._buf[idx + len(marker) :]
                self._in_think = not self._in_think
                continue
            # No complete marker: hold back any trailing partial-tag prefix.
            hold = _max_suffix_prefix(self._buf, marker)
            emit = self._buf[: len(self._buf) - hold]
            if emit:
                out.append(("reasoning_delta" if self._in_think else "delta", emit))
            self._buf = self._buf[len(self._buf) - hold :]
            break
        return out

    def flush(self) -> list[tuple[Kind, str]]:
        """Emit any buffered remainder at end-of-stream."""
        if not self._buf:
            return []
        kind: Kind = "reasoning_delta" if self._in_think else "delta"
        out = [(kind, self._buf)]
        self._buf = ""
        return out


async def stream_chat(
    *,
    model: str,
    messages: list[dict],
    temperature: float,
    top_p: float | None = None,
    think: bool = False,
) -> AsyncIterator[tuple[str, object]]:
    """Stream a chat completion.

    Yields tuples:
      ("reasoning_delta", str) — collapsed thinking text
      ("delta", str)           — visible content
      ("done", dict|None)      — final usage {prompt_tokens, completion_tokens,
                                  total_tokens} if the backend reported it

    Cancellation is handled by the caller cancelling the awaiting task; the
    underlying HTTP stream is closed by the openai client on GeneratorExit.
    """
    extra_body: dict = {}
    if think:
        # Ollama maps this to native thinking mode for capable models.
        extra_body["think"] = True

    stream = await _client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        top_p=top_p,
        stream=True,
        stream_options={"include_usage": True},
        extra_body=extra_body or None,
    )

    splitter = ThinkSplitter()
    usage: dict | None = None
    try:
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                u = chunk.usage
                usage = {
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                    "total_tokens": u.total_tokens,
                }
            for choice in chunk.choices:
                delta = choice.delta
                # (1) explicit reasoning field, if this Ollama build provides it
                extra = getattr(delta, "model_extra", None) or {}
                reasoning = extra.get("reasoning_content") or extra.get("reasoning")
                if reasoning:
                    yield ("reasoning_delta", reasoning)
                # (2) inline <think> parsing on the content stream
                content = delta.content or ""
                if content:
                    for kind, text in splitter.feed(content):
                        yield (kind, text)
        for kind, text in splitter.flush():
            yield (kind, text)
    finally:
        await stream.close()

    yield ("done", usage)


async def complete(
    *,
    model: str,
    messages: list[dict],
    temperature: float,
    top_p: float | None = None,
    think: bool = False,
) -> tuple[str, str]:
    """Non-streaming convenience used by the agent pipeline. Returns
    (content, reasoning)."""
    content: list[str] = []
    reasoning: list[str] = []
    async for kind, data in stream_chat(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        think=think,
    ):
        if kind == "delta":
            content.append(str(data))
        elif kind == "reasoning_delta":
            reasoning.append(str(data))
    return "".join(content), "".join(reasoning)
