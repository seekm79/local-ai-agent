"""Checkpoint (shadow-git) endpoints (Phase 8.2)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import checkpoints

router = APIRouter()


@router.get("/api/projects/{project_id}/checkpoints")
async def list_checkpoints(project_id: int) -> list[dict]:
    return await checkpoints.list_checkpoints(project_id)


class SnapshotBody(BaseModel):
    label: str = "manual checkpoint"


@router.post("/api/projects/{project_id}/checkpoint")
async def snapshot(project_id: int, body: SnapshotBody) -> dict:
    try:
        return await checkpoints.snapshot(project_id, body.label)
    except Exception as exc:
        raise HTTPException(400, f"checkpoint failed: {exc}")


class RestoreBody(BaseModel):
    sha: str


@router.post("/api/projects/{project_id}/restore")
async def restore(project_id: int, body: RestoreBody) -> dict:
    try:
        return await checkpoints.restore(project_id, body.sha)
    except Exception as exc:
        raise HTTPException(400, f"restore failed: {exc}")


@router.get("/api/projects/{project_id}/checkpoint-diff")
async def diff(project_id: int, a: str, b: str) -> dict:
    return {"diff": await checkpoints.diff(project_id, a, b)}
