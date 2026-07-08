"""Automatic context condensing (Phase 8.6).

When a conversation grows past a char threshold, summarize the oldest exchanges
(never the system messages or the most recent N) into a compact memory block via
the small helper model, and replace them. Returns the possibly-shortened message
list plus the summary (or None if nothing was condensed).
"""
from __future__ import annotations

from .. import config
from . import ollama


def estimate_chars(messages: list[dict]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


async def maybe_condense(
    messages: list[dict], helper_model: str
) -> tuple[list[dict], str | None]:
    if estimate_chars(messages) < config.CONDENSE_CHAR_THRESHOLD:
        return messages, None

    system_msgs = [m for m in messages if m.get("role") == "system"]
    convo = [m for m in messages if m.get("role") != "system"]
    keep = config.CONDENSE_KEEP_RECENT
    if len(convo) <= keep + 2:
        return messages, None  # not enough to condense meaningfully

    to_condense = convo[:-keep]
    recent = convo[-keep:]
    transcript = "\n".join(
        f"{m['role']}: {m.get('content','')}" for m in to_condense
    )[:16000]

    try:
        summary, _ = await ollama.complete(
            model=helper_model,
            messages=[
                {"role": "system", "content":
                 "Summarize this earlier conversation into a compact memory block: "
                 "decisions made, files touched, constraints discovered, open "
                 "threads. Terse bullet points."},
                {"role": "user", "content": transcript},
            ],
            temperature=0.3,
        )
    except Exception:
        return messages, None  # best-effort; keep full history on failure

    summary = summary.strip()
    if not summary:
        return messages, None

    memory = {
        "role": "system",
        "content": "[Condensed memory of earlier conversation]\n" + summary,
    }
    return system_msgs + [memory] + recent, summary
