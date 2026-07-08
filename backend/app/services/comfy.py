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
) -> None:
    """Full generation flow. Emits events via on_event(type, payload):
    'progress' {value,max}, 'saved' {path}, 'done' {paths}, 'error' {message}."""
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
            for node in outputs.values():
                for img in node.get("images", []):
                    data_bytes = (
                        await client.get(
                            f"{comfy}/view",
                            params={
                                "filename": img["filename"],
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output"),
                            },
                        )
                    ).content
                    rel = f"assets/{prompt_id[:8]}_{img['filename']}"
                    target = sandbox.resolve_safe(base_dir, rel)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data_bytes)
                    crud.create_asset(
                        project_id,
                        str(target),
                        "image",
                        params.get("positive", ""),
                        template.get("name", workflow_file),
                        json.dumps(params),
                    )
                    saved.append(sandbox.relpath_within(base_dir, target))
                    await on_event("saved", {"path": rel})

        await on_event("done", {"paths": saved})
    except Exception as exc:
        await on_event("error", {"message": f"{type(exc).__name__}: {exc}"})
