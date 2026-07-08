"""Browser tool endpoints (Phase 8.8)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import crud
from ..services import browser

router = APIRouter()


def _base(project_id: int) -> Path:
    proj = crud.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    return Path(proj["path"])


@router.get("/api/browser/status")
async def status() -> dict:
    ok, err = await browser.available()
    return {"available": ok, "error": err}


class BrowserBody(BaseModel):
    url: str | None = None
    actions: list[dict] = []


@router.post("/api/projects/{project_id}/browser")
async def run_browser(project_id: int, body: BrowserBody) -> dict:
    base = _base(project_id)
    artifacts = base / "assets" / "browser"
    result = await browser.run(body.url, body.actions, artifacts)
    urls = []
    for name in result.get("screenshots", []):
        crud.create_asset(
            project_id, str(artifacts / name), "image", None, "browser", None
        )
        urls.append(
            f"/api/projects/{project_id}/raw?path=assets/browser/{name}"
        )
    return {**result, "screenshot_urls": urls}
