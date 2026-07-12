"""Build tab endpoints (Phase 9): scaffold from template, run the Designer ->
Builder chain, manage install/dev processes, and edit the theme palette."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .. import config, crud
from ..services import build, embeddings, ollama, uploads
from ..services.pipeline import pipeline
from ..services.runner import runner
from ..services.sandbox import SandboxError

router = APIRouter()


def _base(project_id: int) -> Path:
    proj = crud.get_project(project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    return Path(proj["path"])


@router.get("/api/build/status")
def status() -> dict:
    return {
        "template_available": build.template_available(),
        "package_manager": config.WEB_PACKAGE_MANAGER,
    }


@router.get("/api/build/projects")
def list_build_projects() -> list[dict]:
    """Build-tab projects (scaffolded from the web template) with each one's
    latest agent run, so the UI can show which are still building and let the
    user re-open a finished or in-flight project."""
    latest: dict[int, dict] = {}
    for r in crud.list_runs():  # newest first — keep the first seen per project
        latest.setdefault(r["project_id"], r)
    out: list[dict] = []
    for p in crud.list_projects():
        base = Path(p["path"])
        if not ((base / "bunfig.toml").is_file() and (base / "package.json").is_file()):
            continue  # not a web-template build project
        run = latest.get(p["id"])
        out.append({
            "id": p["id"],
            "name": p["name"],
            "created_at": p["created_at"],
            "deps_installed": (base / "node_modules").is_dir(),
            "latest_run": {
                "id": run["id"], "status": run["status"], "goal": run["goal"],
            } if run else None,
        })
    return out


class ScaffoldBody(BaseModel):
    name: str
    prompt: str = ""


async def _suggest_name(prompt: str, fallback: str = "") -> str:
    """Generate a concise, human project name from the build prompt via the helper
    model. Falls back to the non-LLM heuristic on empty/garbage/timeout so scaffold
    is never blocked (and never named by cropping the first few words)."""
    heuristic = build.name_from_prompt(prompt) or fallback.strip() or "app"
    text = (prompt or "").strip()
    if len(text) < 8:
        return heuristic
    sys = ("You name software projects. Reply with ONLY a concise project name of "
           "2 to 4 words in Title Case — no quotes, punctuation, or explanation. "
           "Keep acronyms uppercase. Example: Helpdesk CRM")
    try:
        content, _ = await asyncio.wait_for(
            ollama.complete(model=config.MODEL_HELPER,
                            messages=[{"role": "system", "content": sys},
                                      {"role": "user", "content": text[:1500]}],
                            temperature=0.3),
            timeout=25)
    except Exception:
        return heuristic
    return build.clean_name(content) or heuristic


@router.post("/api/build/scaffold")
async def scaffold(body: ScaffoldBody) -> dict:
    if not build.template_available():
        raise HTTPException(412, "web template missing at templates/webapp-base")
    # Derive a proper name from the prompt (the client-sent name is just a fallback).
    name = await _suggest_name(body.prompt, body.name)
    proj = build.scaffold(name, body.prompt)
    # Kick off dependency install as a managed process (streams over /ws/run).
    proc = await runner.start(
        proj["id"], "install deps", build.install_command(), proj["path"]
    )
    # Index the template so the Builder can search shadcn components.
    asyncio.create_task(
        embeddings.index_project(proj["id"], Path(proj["path"]))
    )
    return {"project": proj, "install_proc": proc.public()}


@router.post("/api/build/dev/{project_id}")
async def start_dev(project_id: int) -> dict:
    base = _base(project_id)
    proc = await runner.start(project_id, "dev server", build.dev_command(), str(base))
    return {"proc": proc.public()}


@router.post("/api/build/attach/{project_id}")
async def attach(
    project_id: int,
    role: str = Form("design_reference"),
    file: UploadFile = File(...),
) -> dict:
    if role not in ("design_reference", "asset", "content"):
        raise HTTPException(400, "invalid role")
    base = _base(project_id)
    try:
        info = uploads.save_attachment(
            project_id, base, file.filename or "upload", await file.read(), role
        )
    except SandboxError as exc:
        raise HTTPException(400, str(exc))
    # Interpret image attachments with an installed vision model (best-effort,
    # in the background so the upload responds immediately). The description is
    # merged onto the attachment for the planner/builder to read.
    if info.get("kind") == "image":
        target = base / info["path"]
        purpose = "design reference" if role == "design_reference" else "content image"

        async def _describe(aid: int = info["id"], p=target, pur=purpose) -> None:
            desc = await ollama.describe_image(p, pur)
            if desc:
                uploads.set_description(aid, desc)

        asyncio.create_task(_describe())
    return info


@router.get("/api/build/attachments/{project_id}")
def list_attachments(project_id: int) -> list[dict]:
    return uploads.list_attachments(project_id)


@router.delete("/api/build/attachments/{project_id}/{asset_id}")
def delete_attachment(project_id: int, asset_id: int) -> dict:
    base = _base(project_id)
    if not uploads.delete_attachment(project_id, asset_id, base):
        raise HTTPException(404, "attachment not found")
    return {"status": "deleted"}


class BuildStart(BaseModel):
    project_id: int
    prompt: str
    model: str | None = None
    design_only: bool = False
    generate_images: bool = False
    max_iterations: int = 3


@router.post("/api/build/start")
async def start(body: BuildStart) -> dict:
    proj = crud.get_project(body.project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    run = crud.create_run(body.project_id, body.prompt.strip())
    model = body.model or config.MODEL_CODER
    if "embed" in model.lower():  # embedding models can't chat — fall back
        model = config.MODEL_CODER
    pipeline.start_build(
        run_id=run["id"],
        project_id=body.project_id,
        request=body.prompt.strip(),
        model=model,
        helper_model=config.MODEL_HELPER,
        max_iterations=max(1, body.max_iterations),
        design_only=body.design_only,
        generate_images=body.generate_images,
    )
    return {"run_id": run["id"]}


@router.get("/api/build/palette/{project_id}")
def get_palette(project_id: int) -> dict:
    return build.read_palette(_base(project_id))


class PaletteBody(BaseModel):
    radius: str | None = None
    light: dict = {}
    dark: dict = {}


@router.put("/api/build/palette/{project_id}")
def put_palette(project_id: int, body: PaletteBody) -> dict:
    base = _base(project_id)
    palette = {"light": body.light, "dark": body.dark}
    if body.radius:
        palette["radius"] = body.radius
    build.apply_palette(base, palette)
    return build.read_palette(base)
