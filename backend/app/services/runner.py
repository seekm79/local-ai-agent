"""Subprocess lifecycle: start managed processes, stream output, kill trees.

Two kinds of callers use this:
  * one-click project runners (dotnet run, npm run dev, ...),
  * the confirmed command runner (/api/run/command).

Processes are launched with an explicit argv list — never a shell string with
user/LLM input (Global rule 3 & 4). Output and lifecycle events are published to
subscribers (the /ws/run WebSocket).

Windows notes: there is no SIGTERM/SIGKILL. We launch each process in its own
process group (CREATE_NEW_PROCESS_GROUP) so we can send CTRL_BREAK for a graceful
stop, then fall back to `taskkill /T /F` to kill the whole tree (npm -> node,
dotnet -> child, etc.).
"""
from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import config

_IS_WIN = sys.platform == "win32"

# Detect a dev-server URL in runner output (Vite/Next/etc.). Vite colorizes the
# port, injecting ANSI codes *inside* the URL, so strip ANSI before matching.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/\S*)?")


def _normalize_argv(argv: list[str]) -> list[str]:
    """Windows: resolve argv[0] on PATH and, if it's a .cmd/.bat shim (npm,
    flutter, ...), run it through `cmd /c` — CreateProcess can't exec batch
    files directly. On POSIX, return argv unchanged."""
    if not _IS_WIN or not argv:
        return argv
    resolved = shutil.which(argv[0])
    if not resolved:
        return argv  # let it FileNotFoundError with the original name
    if resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", resolved, *argv[1:]]
    return [resolved, *argv[1:]]


@dataclass
class ProcInfo:
    id: int
    project_id: int
    name: str
    argv: list[str]
    cwd: str
    status: str = "running"  # running | exited | killed
    exit_code: int | None = None
    dev_url: str | None = None
    pid: int | None = None
    _proc: Any = field(default=None, repr=False)

    def public(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "argv": self.argv,
            "status": self.status,
            "exit_code": self.exit_code,
            "dev_url": self.dev_url,
            "pid": self.pid,
        }


class Runner:
    def __init__(self) -> None:
        self._procs: dict[int, ProcInfo] = {}
        self._subs: set[asyncio.Queue] = set()
        self._seq = 0

    # --- pub/sub -------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def _emit(self, type_: str, payload: dict) -> None:
        event = {"type": type_, "payload": payload}
        for q in list(self._subs):
            q.put_nowait(event)

    # --- lifecycle -----------------------------------------------------------
    async def start(
        self, project_id: int, name: str, argv: list[str], cwd: str
    ) -> ProcInfo:
        self._seq += 1
        info = ProcInfo(
            id=self._seq, project_id=project_id, name=name, argv=argv, cwd=cwd
        )

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if _IS_WIN else 0
        try:
            proc = await asyncio.create_subprocess_exec(
                *_normalize_argv(argv),
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except FileNotFoundError:
            info.status = "exited"
            info.exit_code = 127
            self._procs[info.id] = info
            self._emit("run_started", info.public())
            self._emit(
                "run_output",
                {"proc_id": info.id, "data": f"[runner] command not found: {argv[0]}\n"},
            )
            self._emit("run_exited", {"proc_id": info.id, "exit_code": 127})
            return info

        info._proc = proc
        info.pid = proc.pid
        self._procs[info.id] = info
        self._emit("run_started", info.public())
        asyncio.create_task(self._pump(info))
        return info

    async def _pump(self, info: ProcInfo) -> None:
        proc = info._proc
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            if info.dev_url is None:
                m = _URL_RE.search(_ANSI_RE.sub("", text))
                if m:
                    info.dev_url = m.group(0).rstrip("/")
                    self._emit("run_url", {"proc_id": info.id, "url": info.dev_url})
            self._emit("run_output", {"proc_id": info.id, "data": text})

        rc = await proc.wait()
        if info.status == "running":
            info.status = "exited"
        info.exit_code = rc
        self._emit(
            "run_exited",
            {"proc_id": info.id, "exit_code": rc, "status": info.status},
        )

    async def stop(self, proc_id: int) -> bool:
        info = self._procs.get(proc_id)
        if not info or info._proc is None or info.status != "running":
            return False
        proc = info._proc
        info.status = "killed"

        # Graceful first: CTRL_BREAK to the process group (Windows) / terminate.
        try:
            if _IS_WIN:
                proc.send_signal(subprocess.signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                proc.terminate()
        except Exception:
            pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=config.PROCESS_KILL_GRACE_SEC)
        except asyncio.TimeoutError:
            await self._force_kill(proc)
        return True

    async def _force_kill(self, proc: Any) -> None:
        if _IS_WIN:
            # Kill the whole tree (npm -> node, dotnet -> child, ...).
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(proc.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await killer.wait()
            except Exception:
                pass
        else:
            try:
                proc.kill()
            except Exception:
                pass

    def list_for(self, project_id: int) -> list[dict]:
        return [
            p.public() for p in self._procs.values() if p.project_id == project_id
        ]


async def run_capture(
    argv: list[str], cwd: str, timeout: float = 180.0
) -> tuple[int, str]:
    """Run a command to completion, capturing combined stdout/stderr. Used by the
    agent pipeline (reviewer build checks, coder commands). Returns (rc, output).
    rc is 127 if the command is missing, 124 on timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *_normalize_argv(argv),
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return 127, f"command not found: {argv[0]}"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return 124, "timed out"
    return proc.returncode or 0, out.decode("utf-8", errors="replace")


# Singleton used by the router.
runner = Runner()


# --- Project-type detection --------------------------------------------------
def _tool(name: str) -> bool:
    return shutil.which(name) is not None


def detect_runners(base: Path) -> list[dict]:
    """Inspect a project dir and return the runnable actions it supports.

    Each entry: {kind, label, argv, cwd (relative), available, missing_tool}.
    `available` is False when the required CLI isn't on PATH — the UI shows a
    'prerequisite missing' state instead of a dead button.
    """
    out: list[dict] = []

    csproj = next(iter(base.rglob("*.csproj")), None)
    if csproj:
        rel = csproj.parent.relative_to(base)
        out.append(
            {
                "kind": "dotnet",
                "label": "dotnet run",
                "argv": ["dotnet", "run"],
                "cwd": str(rel).replace("\\", "/") if str(rel) != "." else "",
                "available": _tool("dotnet"),
                "missing_tool": "dotnet SDK",
            }
        )

    if (base / "package.json").exists():
        out.append(
            {
                "kind": "node",
                "label": "npm run dev",
                "argv": ["npm", "run", "dev"],
                "cwd": "",
                "available": _tool("npm"),
                "missing_tool": "Node/npm",
            }
        )

    if (base / "pubspec.yaml").exists():
        out.append(
            {
                "kind": "flutter",
                "label": "flutter run -d windows",
                "argv": ["flutter", "run", "-d", "windows"],
                "cwd": "",
                "available": _tool("flutter"),
                "missing_tool": "Flutter SDK",
            }
        )

    if (base / "project.godot").exists():
        out.append(
            {
                "kind": "godot",
                "label": "godot project.godot",
                "argv": ["godot", "project.godot"],
                "cwd": "",
                "available": _tool("godot"),
                "missing_tool": "Godot (add to PATH)",
            }
        )

    return out
