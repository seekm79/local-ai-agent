"""Scoped, sandbox-validated file operations for a project.

Every `path` from the client passes through `_safe()` -> `sandbox.resolve_safe`
before any filesystem access (Global rule 2). Paths in responses are relative
to the project root (POSIX style).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import crud
from ..services import sandbox
from ..services.sandbox import SandboxError

router = APIRouter()

# Reject reading files above this size as text (keeps the editor responsive).
MAX_TEXT_BYTES = 2_000_000

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".ogv"}
_SKIP_DIRS = {"obj", "bin", "node_modules", ".git", ".vs"}


def _base(project_id: int) -> Path:
    proj = crud.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    return Path(proj["path"])


def _safe(base: Path, path: str | None) -> Path:
    try:
        return sandbox.resolve_safe(base, path)
    except SandboxError as exc:
        raise HTTPException(400, str(exc))


def _entry(base: Path, p: Path) -> dict:
    return {
        "name": p.name,
        "path": sandbox.relpath_within(base, p),
        "type": "dir" if p.is_dir() else "file",
    }


@router.get("/api/projects/{project_id}/tree")
def tree(project_id: int, path: str = "") -> list[dict]:
    """List one directory level (lazy tree loading)."""
    base = _base(project_id)
    target = _safe(base, path)
    if not target.is_dir():
        raise HTTPException(400, "not a directory")
    children = sorted(
        target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
    )
    return [_entry(base, c) for c in children]


@router.get("/api/projects/{project_id}/read")
def read_file(project_id: int, path: str) -> dict:
    base = _base(project_id)
    target = _safe(base, path)
    if not target.is_file():
        raise HTTPException(404, "file not found")
    if target.stat().st_size > MAX_TEXT_BYTES:
        raise HTTPException(413, "file too large to open as text")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "binary file — cannot open as text")
    return {"path": sandbox.relpath_within(base, target), "content": content}


class WriteBody(BaseModel):
    path: str
    content: str


@router.put("/api/projects/{project_id}/write")
def write_file(project_id: int, body: WriteBody) -> dict:
    base = _base(project_id)
    target = _safe(base, body.path)
    if target.is_dir():
        raise HTTPException(400, "path is a directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    return {"status": "ok", "path": sandbox.relpath_within(base, target)}


class CreateBody(BaseModel):
    path: str
    is_dir: bool = False


@router.post("/api/projects/{project_id}/create")
def create_entry(project_id: int, body: CreateBody) -> dict:
    base = _base(project_id)
    target = _safe(base, body.path)
    if target.exists():
        raise HTTPException(409, "path already exists")
    if body.is_dir:
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    return _entry(base, target)


class RenameBody(BaseModel):
    path: str
    new_path: str


@router.post("/api/projects/{project_id}/rename")
def rename_entry(project_id: int, body: RenameBody) -> dict:
    base = _base(project_id)
    src = _safe(base, body.path)
    dst = _safe(base, body.new_path)
    if not src.exists():
        raise HTTPException(404, "source not found")
    if dst.exists():
        raise HTTPException(409, "destination already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return _entry(base, dst)


@router.delete("/api/projects/{project_id}/delete")
def delete_entry(project_id: int, path: str) -> dict:
    base = _base(project_id)
    target = _safe(base, path)
    if not target.exists():
        raise HTTPException(404, "not found")
    if target == sandbox._real(base):
        raise HTTPException(400, "cannot delete the project root")
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    else:
        target.unlink(missing_ok=True)
    return {"status": "ok"}


@router.get("/api/projects/{project_id}/all-files")
def all_files(project_id: int) -> list[str]:
    """Flat list of all file paths in the project (for Cmd+P quick-open)."""
    base = sandbox._real(_base(project_id))
    out: list[str] = []
    for p in sorted(base.rglob("*")):
        if any(part in _SKIP_DIRS for part in p.relative_to(base).parts):
            continue
        if p.is_file():
            out.append(sandbox.relpath_within(base, p))
        if len(out) >= 5000:
            break
    return out


@router.get("/api/projects/{project_id}/media")
def media(project_id: int) -> list[dict]:
    """List image/video files anywhere in the project (for the Assets gallery)."""
    base = sandbox._real(_base(project_id))
    items: list[dict] = []
    for p in sorted(base.rglob("*")):
        if any(part in _SKIP_DIRS for part in p.relative_to(base).parts):
            continue
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        kind = "image" if ext in IMAGE_EXT else "video" if ext in VIDEO_EXT else None
        if kind:
            items.append(
                {"name": p.name, "path": sandbox.relpath_within(base, p), "kind": kind}
            )
    return items


@router.get("/api/projects/{project_id}/raw")
def raw(project_id: int, path: str) -> FileResponse:
    """Serve a project file with the correct content-type. Starlette's
    FileResponse honors the Range header, which video seeking needs. Path is
    sandbox-validated (Global rule 2)."""
    base = _base(project_id)
    target = _safe(base, path)
    if not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target)


@router.post("/api/projects/{project_id}/upload")
async def upload(
    project_id: int,
    path: str = Form(""),
    files: list[UploadFile] = File(...),
) -> dict:
    """Upload one or more files into a project directory (defaults to root)."""
    base = _base(project_id)
    dest_dir = _safe(base, path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for f in files:
        name = (f.filename or "upload").replace("\\", "/").split("/")[-1]
        rel = f"{path.rstrip('/')}/{name}" if path else name
        target = _safe(base, rel)
        target.write_bytes(await f.read())
        saved.append(sandbox.relpath_within(base, target))
    return {"saved": saved}
