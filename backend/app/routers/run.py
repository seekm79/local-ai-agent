"""Terminal + command/project runners (Phase 3).

WS /ws/terminal  — interactive PTY shell (PowerShell on Windows), cwd = project.
WS /ws/run       — broadcast of managed-process lifecycle + output events.
REST /api/run/*  — detect runners, start project runners, command runner with the
                   confirmation flow (Global rule 3), stop, list processes.

All process launches use an explicit argv list (never a shell string). Dangerous
commands pause for user confirmation via a one-time token.
"""
from __future__ import annotations

import asyncio
import secrets
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .. import config, crud
from ..services import sandbox
from ..services.runner import detect_runners, runner
from ..services.sandbox import SandboxError

router = APIRouter()

# Pending confirmations: token -> launch spec. One-time use.
_pending: dict[str, dict] = {}


def _project_base(project_id: int) -> Path:
    proj = crud.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    return Path(proj["path"])


def _safe_cwd(project_id: int, rel: str) -> str:
    base = _project_base(project_id)
    try:
        target = sandbox.resolve_safe(base, rel or "")
    except SandboxError as exc:
        raise HTTPException(400, str(exc))
    if not target.is_dir():
        raise HTTPException(400, "cwd is not a directory")
    return str(target)


# --- REST: detection & runners ----------------------------------------------
@router.get("/api/run/detect")
def detect(project_id: int) -> list[dict]:
    return detect_runners(_project_base(project_id))


@router.get("/api/run/processes")
def processes(project_id: int) -> list[dict]:
    return runner.list_for(project_id)


class ProjectRun(BaseModel):
    project_id: int
    kind: str


@router.post("/api/run/project")
async def run_project(body: ProjectRun) -> dict:
    base = _project_base(body.project_id)
    match = next((r for r in detect_runners(base) if r["kind"] == body.kind), None)
    if not match:
        raise HTTPException(404, f"no {body.kind} runner detected")
    if not match["available"]:
        raise HTTPException(
            412, f"{match['missing_tool']} not found on PATH — install it first"
        )
    cwd = _safe_cwd(body.project_id, match["cwd"])
    info = await runner.start(body.project_id, match["label"], match["argv"], cwd)
    return {"status": "started", "proc": info.public()}


class CommandRun(BaseModel):
    project_id: int
    argv: list[str]
    cwd: str = ""


@router.post("/api/run/command")
async def run_command(body: CommandRun) -> dict:
    if not body.argv:
        raise HTTPException(400, "empty command")
    cwd = _safe_cwd(body.project_id, body.cwd)

    if sandbox.command_needs_confirmation(body.argv):
        token = secrets.token_hex(16)
        _pending[token] = {
            "project_id": body.project_id,
            "argv": body.argv,
            "cwd": cwd,
        }
        return {
            "status": "needs_confirmation",
            "command": " ".join(body.argv),
            "token": token,
        }

    info = await runner.start(
        body.project_id, " ".join(body.argv), body.argv, cwd
    )
    return {"status": "started", "proc": info.public()}


class Confirm(BaseModel):
    token: str


@router.post("/api/run/confirm")
async def confirm(body: Confirm) -> dict:
    spec = _pending.pop(body.token, None)
    if not spec:
        raise HTTPException(400, "invalid or already-used confirmation token")
    info = await runner.start(
        spec["project_id"], " ".join(spec["argv"]), spec["argv"], spec["cwd"]
    )
    return {"status": "started", "proc": info.public()}


class Stop(BaseModel):
    proc_id: int


@router.post("/api/run/stop")
async def stop(body: Stop) -> dict:
    ok = await runner.stop(body.proc_id)
    if not ok:
        raise HTTPException(404, "process not running")
    return {"status": "stopping"}


# --- WS: process event broadcast --------------------------------------------
@router.websocket("/ws/run")
async def ws_run(ws: WebSocket) -> None:
    await ws.accept()
    q = runner.subscribe()
    try:
        while True:
            event = await q.get()
            await ws.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        runner.unsubscribe(q)


# --- WS: interactive PTY terminal -------------------------------------------
async def _safe_send(ws: WebSocket, msg: dict) -> None:
    try:
        await ws.send_json(msg)
    except Exception:
        pass


@router.websocket("/ws/terminal")
async def ws_terminal(ws: WebSocket, project_id: int) -> None:
    await ws.accept()
    proj = crud.get_project(project_id)
    if not proj:
        await _safe_send(ws, {"type": "error", "payload": {"message": "project not found"}})
        await ws.close()
        return

    try:
        from winpty import PtyProcess
    except ImportError:
        await _safe_send(
            ws,
            {"type": "error", "payload": {"message": "Interactive terminal requires pywinpty (Windows)."}},
        )
        await ws.close()
        return

    cwd = str(Path(proj["path"]))
    pty = PtyProcess.spawn(config.TERMINAL_SHELL, cwd=cwd, dimensions=(24, 80))
    loop = asyncio.get_running_loop()
    stop_flag = threading.Event()

    def reader() -> None:
        # pywinpty reads block; run in a thread and marshal back to the loop.
        while not stop_flag.is_set():
            try:
                data = pty.read(4096)
            except EOFError:
                break
            if data:
                asyncio.run_coroutine_threadsafe(
                    _safe_send(ws, {"type": "output", "payload": {"data": data}}), loop
                )
        asyncio.run_coroutine_threadsafe(
            _safe_send(ws, {"type": "exit", "payload": {}}), loop
        )

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")
            payload = msg.get("payload", {})
            if mtype == "input":
                pty.write(payload.get("data", ""))
            elif mtype == "resize":
                try:
                    pty.setwinsize(int(payload["rows"]), int(payload["cols"]))
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        stop_flag.set()
        try:
            pty.terminate(force=True)
        except Exception:
            pass
