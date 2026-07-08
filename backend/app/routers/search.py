"""Codebase search endpoints (Phase 8.3)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import crud
from ..services import embeddings

router = APIRouter()


def _base(project_id: int) -> Path:
    proj = crud.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    return Path(proj["path"])


@router.get("/api/projects/{project_id}/index-status")
async def index_status(project_id: int) -> dict:
    ok, err = await embeddings.available()
    return {
        "available": ok,
        "error": err,
        "chunks": embeddings.chunk_count(project_id),
        "model": embeddings.config.MODEL_EMBED,
    }


@router.post("/api/projects/{project_id}/index")
async def index(project_id: int, force: bool = False) -> dict:
    ok, err = await embeddings.available()
    if not ok:
        raise HTTPException(412, err or "embedding model unavailable")
    return await embeddings.index_project(project_id, _base(project_id), force=force)


@router.get("/api/projects/{project_id}/search")
async def search(project_id: int, q: str, k: int = 6) -> dict:
    ok, err = await embeddings.available()
    if not ok:
        raise HTTPException(412, err or "embedding model unavailable")
    if embeddings.chunk_count(project_id) == 0:
        # auto-index on first search so the box "just works"
        await embeddings.index_project(project_id, _base(project_id))
    results = await embeddings.search(project_id, q, k)
    return {"results": results}
