"""Checkpoint (shadow-git) snapshot/restore tests (Phase 8.2)."""
from __future__ import annotations

import pytest

from app import config, crud
from app.services import checkpoints


@pytest.fixture()
def project(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(config, "PROJECTS_ROOT", root)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "wb.db")
    from app.db import init_db

    init_db()
    proj_dir = root / "demo"
    proj_dir.mkdir(parents=True)
    (proj_dir / "main.cs").write_text("original\n", encoding="utf-8")
    proj = crud.create_project("demo", "demo", str(proj_dir))
    return proj["id"], proj_dir


@pytest.mark.asyncio
async def test_snapshot_and_list(project):
    pid, _ = project
    cp = await checkpoints.snapshot(pid, "first")
    assert len(cp["sha"]) >= 7
    items = await checkpoints.list_checkpoints(pid)
    assert items and items[0]["label"] == "first"


@pytest.mark.asyncio
async def test_restore_reverts_bad_edit(project):
    pid, proj_dir = project
    good = await checkpoints.snapshot(pid, "good state")

    # a "bad edit"
    (proj_dir / "main.cs").write_text("BROKEN GARBAGE\n", encoding="utf-8")
    await checkpoints.snapshot(pid, "bad edit")
    assert "BROKEN" in (proj_dir / "main.cs").read_text(encoding="utf-8")

    # restore to the good checkpoint
    await checkpoints.restore(pid, good["sha"])
    assert (proj_dir / "main.cs").read_text(encoding="utf-8") == "original\n"


@pytest.mark.asyncio
async def test_shadow_repo_isolated(project):
    pid, proj_dir = project
    await checkpoints.snapshot(pid, "x")
    # snapshot lives in .workbench, not a top-level .git
    assert (proj_dir / ".workbench" / "checkpoints.git").exists()
    assert not (proj_dir / ".git").exists()
