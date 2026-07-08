"""Custom agent modes CRUD (Phase 8.4)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import modes

router = APIRouter()


class ModeBody(BaseModel):
    slug: str
    name: str
    system_prompt: str = ""
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    allowed_tools: list[str] = []
    file_globs: list[str] = []


@router.get("/api/modes")
def list_modes() -> list[dict]:
    return modes.list_modes()


@router.get("/api/modes/tools")
def all_tools() -> list[str]:
    return modes.ALL_TOOLS


@router.put("/api/modes/{slug}")
def upsert(slug: str, body: ModeBody) -> dict:
    data = body.model_dump()
    data["slug"] = slug
    return modes.upsert_mode(data)


@router.delete("/api/modes/{slug}")
def delete(slug: str) -> dict:
    if not modes.delete_mode(slug):
        raise HTTPException(400, "cannot delete a built-in or missing mode")
    return {"status": "deleted"}
