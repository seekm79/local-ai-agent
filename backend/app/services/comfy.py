"""ComfyUI integration: load API-format workflow templates, substitute the
declared parameter slots, submit to ComfyUI, follow progress over its WebSocket,
fetch the output images, and save them into the active project's assets/.

Workflow template files live in `workflows/*.json` and wrap a ComfyUI API-format
graph with a `slots` declaration and `{{key}}` placeholders (see
`workflows/txt2img.json`). This lets the UI generate a parameter form.

ComfyUI is optional. Every entry point degrades gracefully when it is not
running at COMFY_BASE_URL (Global rule 7 — surface a clear offline state).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
import websockets

from .. import config, crud
from . import sandbox

ProgressCb = Callable[[str, dict], Awaitable[None]]


# --- Workflow templates ------------------------------------------------------
def list_workflows() -> list[dict]:
    """Return {name, file, description, slots} for each workflow template."""
    out: list[dict] = []
    if not config.WORKFLOWS_DIR.is_dir():
        return out
    for f in sorted(config.WORKFLOWS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(
            {
                "file": f.name,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "slots": data.get("slots", []),
            }
        )
    return out


def load_workflow(file: str) -> dict:
    """Load one template by file name (validated to stay inside WORKFLOWS_DIR)."""
    target = (config.WORKFLOWS_DIR / Path(file).name).resolve()
    if target.parent != config.WORKFLOWS_DIR.resolve() or not target.is_file():
        raise FileNotFoundError(f"workflow not found: {file}")
    return json.loads(target.read_text(encoding="utf-8"))


def _coerce(value: Any, type_: str) -> Any:
    if type_ == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if type_ == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return value


def substitute(template: dict, params: dict) -> dict:
    """Produce a ComfyUI API-format graph from a template + user params.

    A value that is exactly ``"{{key}}"`` is replaced by the typed param (an int
    stays an int); ``{{key}}`` appearing inside a larger string is str-replaced.
    """
    slots = {s["key"]: s for s in template.get("slots", [])}
    values = {
        key: _coerce(params.get(key, slot.get("default")), slot.get("type", "text"))
        for key, slot in slots.items()
    }

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            for key, val in values.items():
                token = "{{" + key + "}}"
                if node == token:
                    return val  # typed replacement (keeps ints as ints)
                if token in node:
                    node = node.replace(token, str(val))
            return node
        return node

    return walk(template["workflow"])


# --- ComfyUI connectivity ----------------------------------------------------
async def check_online() -> tuple[bool, str | None]:
    """Ping ComfyUI's /system_stats. Returns (online, error_message)."""
    url = f"{config.COMFY_BASE_URL.rstrip('/')}/system_stats"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return True, None
    except Exception as exc:
        return False, f"ComfyUI not detected at {config.COMFY_BASE_URL} ({type(exc).__name__})"


async def list_installed_checkpoints() -> list[str]:
    """Ask the live ComfyUI which checkpoints are actually installed. Empty on
    failure — callers treat that as 'can't verify, leave the graph as-is'."""
    url = f"{config.COMFY_BASE_URL.rstrip('/')}/object_info/CheckpointLoaderSimple"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            data = (await client.get(url)).json()
        return list(data["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
    except Exception:
        return []


# Substrings that mark a checkpoint as a video/animation model — used to keep an
# image workflow from grabbing a video model (and vice-versa) when auto-repairing.
_VIDEO_CKPT_HINTS = ("ltx", "svd", "video", "wan", "hunyuan", "mochi", "cosmos", "animate")


def _pick_checkpoint(available: list[str], want_video: bool) -> str | None:
    """Choose an installed checkpoint of the right kind, else any installed one."""
    def is_video(name: str) -> bool:
        return any(h in name.lower() for h in _VIDEO_CKPT_HINTS)

    preferred = [c for c in available if is_video(c) == want_video]
    return (preferred or available or [None])[0]


def repair_checkpoints(graph: dict, available: list[str], want_video: bool) -> list[str]:
    """Swap any CheckpointLoaderSimple whose ckpt_name isn't installed for one
    that is. Mutates `graph` in place; returns human-readable notes about swaps so
    the caller can surface them instead of failing silently (reliability)."""
    notes: list[str] = []
    if not available:
        return notes
    for node in graph.values():
        if not isinstance(node, dict) or node.get("class_type") != "CheckpointLoaderSimple":
            continue
        current = node.get("inputs", {}).get("ckpt_name")
        if current in available:
            continue
        replacement = _pick_checkpoint(available, want_video)
        if replacement:
            node["inputs"]["ckpt_name"] = replacement
            notes.append(f"checkpoint '{current}' not installed — using '{replacement}'")
    return notes


def _ws_url(client_id: str) -> str:
    base = config.COMFY_BASE_URL.rstrip("/")
    scheme = "wss" if base.startswith("https") else "ws"
    host = base.split("://", 1)[-1]
    return f"{scheme}://{host}/ws?clientId={client_id}"


async def generate(
    project_id: int,
    workflow_file: str,
    params: dict,
    on_event: ProgressCb,
    dest_rel: str | None = None,
) -> None:
    """Full generation flow. Emits events via on_event(type, payload):
    'progress' {value,max}, 'saved' {path}, 'done' {paths}, 'error' {message}.

    If ``dest_rel`` is given, the first output is written to that exact project-
    relative path (e.g. ``public/hero.png``) instead of an auto name under
    assets/, so generated code can reference a known URL. The extension is
    forced to match the actual output so an animated webp stays a .webp."""
    online, err = await check_online()
    if not online:
        await on_event("error", {"message": err or "ComfyUI offline"})
        return

    proj = crud.get_project(project_id)
    if not proj:
        await on_event("error", {"message": "project not found"})
        return
    base_dir = Path(proj["path"])

    try:
        template = load_workflow(workflow_file)
        graph = substitute(template, params)
    except Exception as exc:
        await on_event("error", {"message": f"workflow error: {exc}"})
        return

    # Auto-adapt to the models this ComfyUI actually has, so a workflow authored
    # against a different machine's checkpoint still runs instead of erroring.
    want_video = template.get("kind") == "video"
    for note in repair_checkpoints(graph, await list_installed_checkpoints(), want_video):
        await on_event("note", {"message": note})

    client_id = uuid.uuid4().hex
    comfy = config.COMFY_BASE_URL.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{comfy}/prompt", json={"prompt": graph, "client_id": client_id}
            )
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]

        # Follow progress over ComfyUI's WebSocket until execution completes.
        async with websockets.connect(_ws_url(client_id), max_size=None) as ws:
            while True:
                raw = await ws.recv()
                if isinstance(raw, bytes):
                    continue  # preview frames — ignore
                msg = json.loads(raw)
                mtype = msg.get("type")
                data = msg.get("data", {})
                if mtype == "progress":
                    await on_event(
                        "progress",
                        {"value": data.get("value"), "max": data.get("max")},
                    )
                elif mtype == "execution_error":
                    await on_event("error", {"message": str(data)})
                    return
                elif mtype == "executing":
                    if data.get("node") is None and data.get("prompt_id") == prompt_id:
                        break  # done

        # Fetch outputs from history and save them into the project.
        async with httpx.AsyncClient(timeout=60.0) as client:
            hist = (await client.get(f"{comfy}/history/{prompt_id}")).json()
            outputs = hist.get(prompt_id, {}).get("outputs", {})
            saved: list[str] = []
            # ComfyUI reports still images under 'images'; animated/video nodes
            # (SaveAnimatedWEBP/PNG, VHS_VideoCombine, LTX savers) use 'images',
            # 'gifs', or 'videos'. Capture them all so animations aren't dropped.
            first = True
            for node in outputs.values():
                for key in ("images", "gifs", "videos"):
                    for out in node.get(key, []):
                        data_bytes = (
                            await client.get(
                                f"{comfy}/view",
                                params={
                                    "filename": out["filename"],
                                    "subfolder": out.get("subfolder", ""),
                                    "type": out.get("type", "output"),
                                },
                            )
                        ).content
                        actual_ext = Path(out["filename"]).suffix
                        if dest_rel and first:
                            # write the primary output to the caller's chosen path,
                            # but keep the real extension so the file stays valid.
                            rel = str(Path(dest_rel).with_suffix(actual_ext))
                        else:
                            rel = f"assets/{prompt_id[:8]}_{out['filename']}"
                        first = False
                        target = sandbox.resolve_safe(base_dir, rel)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data_bytes)
                        ext = Path(out["filename"]).suffix.lower()
                        kind = "video" if ext in (".mp4", ".webm", ".gif", ".webp") else "image"
                        crud.create_asset(
                            project_id,
                            str(target),
                            kind,
                            params.get("positive", ""),
                            template.get("name", workflow_file),
                            json.dumps(params),
                        )
                        saved.append(sandbox.relpath_within(base_dir, target))
                        await on_event("saved", {"path": rel, "kind": kind})

        await on_event("done", {"paths": saved})
    except Exception as exc:
        await on_event("error", {"message": f"{type(exc).__name__}: {exc}"})
