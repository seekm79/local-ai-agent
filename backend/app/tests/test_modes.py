"""Custom mode tests (Phase 8.4)."""
from __future__ import annotations

import pytest

from app import config
from app.services import modes


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "m.db")
    from app.db import init_db

    init_db()
    modes.seed_defaults()
    yield


def test_defaults_seeded():
    slugs = {m["slug"] for m in modes.list_modes()}
    assert {"architect", "coder", "reviewer", "ask"} <= slugs


def test_tool_allowed():
    reviewer = modes.get_mode("reviewer")
    assert modes.tool_allowed(reviewer, "run_command") is True
    assert modes.tool_allowed(reviewer, "write_file") is False
    assert modes.tool_allowed(None, "anything") is True  # no mode = unrestricted


def test_path_allowed_globs():
    docs = modes.upsert_mode(
        {"slug": "docs", "name": "Docs", "allowed_tools": ["apply_diff"],
         "file_globs": ["*.md"]}
    )
    assert modes.path_allowed(docs, "README.md") is True
    assert modes.path_allowed(docs, "docs/guide.md") is True
    assert modes.path_allowed(docs, "src/App.tsx") is False
    # empty globs = all allowed
    assert modes.path_allowed(modes.get_mode("coder"), "anything.rs") is True


def test_cannot_delete_builtin():
    assert modes.delete_mode("coder") is False


def test_can_delete_custom():
    modes.upsert_mode({"slug": "temp", "name": "Temp"})
    assert modes.delete_mode("temp") is True
    assert modes.get_mode("temp") is None
