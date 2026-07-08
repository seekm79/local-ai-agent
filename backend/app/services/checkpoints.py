"""Checkpoints + rollback (Phase 8.2).

Snapshots the project into a SHADOW git repo at
`<project>/.workbench/checkpoints.git` with the project as its work tree. The
user's own `.git` (if any) is never touched. Restore is `reset --hard` to a
checkpoint, so a bad edit to a tracked file is one click from undone.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from .. import crud

_EXCLUDES = [
    ".workbench/",
    "node_modules/",
    "obj/",
    "bin/",
    ".git/",
    "dist/",
    ".vs/",
    "__pycache__/",
]


def _base(project_id: int) -> Path:
    proj = crud.get_project(project_id)
    if not proj:
        raise ValueError("project not found")
    return Path(proj["path"])


def _shadow(base: Path) -> Path:
    return base / ".workbench" / "checkpoints.git"


async def _git(base: Path, *args: str) -> tuple[int, str]:
    cmd = [
        "git",
        "--git-dir",
        str(_shadow(base)),
        "--work-tree",
        str(base),
        *args,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", errors="replace")


async def _ensure(base: Path) -> None:
    if _shadow(base).exists():
        return
    _shadow(base).parent.mkdir(parents=True, exist_ok=True)
    await _git(base, "init", "-q")
    exclude = _shadow(base) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("\n".join(_EXCLUDES) + "\n", encoding="utf-8")
    await _git(base, "config", "user.email", "workbench@local")
    await _git(base, "config", "user.name", "Workbench")
    await _git(base, "config", "commit.gpgsign", "false")


async def snapshot(project_id: int, label: str) -> dict:
    """Commit the current project state. Returns {sha, label}."""
    base = _base(project_id)
    await _ensure(base)
    await _git(base, "add", "-A")
    await _git(base, "commit", "--allow-empty", "-q", "-m", label)
    _, sha = await _git(base, "rev-parse", "HEAD")
    return {"sha": sha.strip()[:12], "label": label}


async def list_checkpoints(project_id: int) -> list[dict]:
    base = _base(project_id)
    if not _shadow(base).exists():
        return []
    rc, out = await _git(
        base, "log", "--pretty=%H%x1f%s%x1f%cI", "-n", "200"
    )
    if rc != 0:
        return []
    items: list[dict] = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            items.append(
                {"sha": parts[0][:12], "label": parts[1], "time": parts[2]}
            )
    return items


async def restore(project_id: int, sha: str) -> dict:
    """Reset the project's tracked files to a checkpoint."""
    base = _base(project_id)
    if not _shadow(base).exists():
        raise ValueError("no checkpoints for this project")
    rc, out = await _git(base, "reset", "--hard", sha)
    if rc != 0:
        raise ValueError(f"restore failed: {out.strip()}")
    return {"status": "restored", "sha": sha[:12]}


async def diff(project_id: int, a: str, b: str) -> str:
    base = _base(project_id)
    if not _shadow(base).exists():
        return ""
    _, out = await _git(base, "diff", a, b)
    return out
