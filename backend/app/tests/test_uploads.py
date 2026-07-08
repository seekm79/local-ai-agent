"""Build upload/attachment tests (Phase 9.10/9.11)."""
from __future__ import annotations

import pytest

from app import config, crud
from app.services import uploads


def test_rgb_to_oklch_known_values():
    # sRGB red ≈ oklch(0.628 0.258 29.2)
    assert uploads.rgb_to_oklch(255, 0, 0).startswith("oklch(0.628")
    assert uploads.rgb_to_oklch(255, 255, 255).startswith("oklch(1.000")
    assert uploads.rgb_to_oklch(0, 0, 0).startswith("oklch(0.000")


def test_dest_rel_by_role():
    assert uploads._dest_rel("asset", "logo.png") == "public/logo.png"
    assert uploads._dest_rel("content", "data.csv") == "uploads/data.csv"
    assert uploads._dest_rel("design_reference", "ref.png").startswith("assets/references/")


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "ws")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "u.db")
    from app.db import init_db

    init_db()
    d = (tmp_path / "ws" / "app")
    d.mkdir(parents=True)
    proj = crud.create_project("app", "app", str(d))
    return proj["id"], d


def test_save_content_extracts_text(project):
    pid, base = project
    res = uploads.save_attachment(pid, base, "data.csv", b"name,age\nAda,36\n", "content")
    assert res["role"] == "content"
    assert (base / "uploads" / "data.csv").is_file()
    atts = uploads.list_attachments(pid)
    assert atts[0]["role"] == "content"
    assert "Ada" in atts[0]["text"]


def test_save_asset_to_public(project):
    pid, base = project
    uploads.save_attachment(pid, base, "logo.svg", b"<svg/>", "asset")
    assert (base / "public" / "logo.svg").is_file()


def test_attachment_filename_sanitized(project):
    pid, base = project
    # a traversal-y filename is reduced to its basename and stays in the project
    res = uploads.save_attachment(pid, base, "../../evil.txt", b"x", "content")
    assert res["path"] == "uploads/evil.txt"
    assert (base / "uploads" / "evil.txt").is_file()
    assert not (base.parent.parent / "evil.txt").exists()
