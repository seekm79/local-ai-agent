"""Project CRUD.

Creating a project makes `workspace/<slug>/` with an `assets/` subfolder.
Deleting archives the DB row by default and never touches files on disk unless
`delete_files=true` is passed (the frontend gates that behind a confirm modal).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config, crud
from ..services import sandbox
from ..services.projects_util import slugify

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str


@router.get("/api/projects")
def list_projects() -> list[dict]:
    return crud.list_projects()


@router.post("/api/projects")
def create_project(body: ProjectCreate) -> dict:
    name = body.name.strip() or "Untitled"
    base_slug = slugify(name)
    slug, i = base_slug, 2
    while crud.slug_exists(slug):
        slug, i = f"{base_slug}-{i}", i + 1

    proj_dir = (config.PROJECTS_ROOT / slug).resolve()
    # Confirm the target really lands inside the projects root before creating.
    if not sandbox._is_within(proj_dir, sandbox.projects_root()):
        raise HTTPException(400, "invalid project location")
    (proj_dir / "assets").mkdir(parents=True, exist_ok=True)

    return crud.create_project(name, slug, str(proj_dir))


@router.get("/api/projects/{project_id}")
def get_project(project_id: int) -> dict:
    proj = crud.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    return proj


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: int, delete_files: bool = False) -> dict:
    proj = crud.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")

    if delete_files:
        base = Path(proj["path"])
        # Only ever rmtree inside the projects root.
        if sandbox._is_within(sandbox._real(base), sandbox.projects_root()):
            shutil.rmtree(base, ignore_errors=True)
        crud.delete_project_row(project_id)
    else:
        crud.archive_project(project_id)

    return {"status": "ok", "deleted_files": delete_files}
