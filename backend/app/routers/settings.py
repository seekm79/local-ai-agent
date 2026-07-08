"""Settings screen backend (Phase 7): read + update runtime settings."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import settings

router = APIRouter()


@router.get("/api/settings")
def get_settings() -> dict:
    return settings.get_all()


@router.put("/api/settings")
async def put_settings(body: dict) -> dict:
    try:
        return settings.update(body)
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(400, f"invalid setting: {exc}")
