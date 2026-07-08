"""Settings hot-reload tests (Phase 7)."""
from __future__ import annotations

import pytest

from app import config
from app.services import sandbox, settings


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    # Point the DB at a temp file so update() doesn't touch the real one.
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "s.db")
    from app.db import init_db

    init_db()
    yield


def test_get_all_has_expected_keys():
    keys = settings.get_all().keys()
    for k in ("model_planner", "chat_temperature", "deny_commands", "comfy_base_url"):
        assert k in keys


def test_update_applies_to_config_live(monkeypatch):
    monkeypatch.setattr(config, "MODEL_PLANNER", "old")
    result = settings.update({"model_planner": "codegemma:7b"})
    assert config.MODEL_PLANNER == "codegemma:7b"  # hot-applied
    assert result["model_planner"] == "codegemma:7b"


def test_update_coerces_types(monkeypatch):
    settings.update({"context_char_budget": "8000", "coding_top_p": "0.9"})
    assert config.CONTEXT_CHAR_BUDGET == 8000
    assert isinstance(config.CONTEXT_CHAR_BUDGET, int)
    assert config.CODING_TOP_P == 0.9


def test_deny_list_edit_affects_sandbox(monkeypatch):
    monkeypatch.setattr(config, "DENY_COMMANDS", ["rm"])
    assert sandbox.command_needs_confirmation(["mytool"]) is False
    settings.update({"deny_commands": ["rm", "mytool"]})
    assert sandbox.command_needs_confirmation(["mytool"]) is True


def test_update_rejects_bad_number(monkeypatch):
    with pytest.raises((ValueError, TypeError)):
        settings.update({"context_char_budget": "not-a-number"})
