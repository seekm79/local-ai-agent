"""Runtime settings: persist user overrides to the `settings` table and apply
them onto the `config` module so reads hot-reload without a restart.

Most of the codebase reads `config.X` at call time (inside request handlers), so
mutating `config` attributes here takes effect immediately. A few things (the
Ollama client base URL, bound host/port) are import-time and are intentionally
not exposed as editable settings.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config
from ..db import get_conn

# field key -> (config attribute, type)
_FIELDS: dict[str, tuple[str, str]] = {
    "projects_root": ("PROJECTS_ROOT", "path"),
    "model_big": ("MODEL_BIG", "str"),
    "model_planner": ("MODEL_PLANNER", "str"),
    "model_coder": ("MODEL_CODER", "str"),
    "model_reviewer": ("MODEL_REVIEWER", "str"),
    "model_helper": ("MODEL_HELPER", "str"),
    "chat_temperature": ("CHAT_TEMPERATURE", "float"),
    "coding_temperature": ("CODING_TEMPERATURE", "float"),
    "coding_top_p": ("CODING_TOP_P", "float"),
    "context_char_budget": ("CONTEXT_CHAR_BUDGET", "int"),
    "comfy_base_url": ("COMFY_BASE_URL", "str"),
    "deny_commands": ("DENY_COMMANDS", "list"),
}


def _coerce(value: object, type_: str) -> object:
    if type_ == "int":
        return int(value)  # type: ignore[arg-type]
    if type_ == "float":
        return float(value)  # type: ignore[arg-type]
    if type_ == "path":
        return Path(str(value)).resolve()
    if type_ == "list":
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [s.strip() for s in str(value).splitlines() if s.strip()]
    return str(value)


def _apply(key: str, value: object) -> None:
    attr, type_ = _FIELDS[key]
    coerced = _coerce(value, type_)
    if type_ == "path":
        Path(str(coerced)).mkdir(parents=True, exist_ok=True)
    setattr(config, attr, coerced)


def _serializable(key: str) -> object:
    attr, type_ = _FIELDS[key]
    val = getattr(config, attr)
    return str(val) if type_ == "path" else val


def get_all() -> dict:
    """Effective current settings (config defaults + persisted overrides)."""
    return {key: _serializable(key) for key in _FIELDS}


def load() -> None:
    """Apply persisted overrides onto config at startup."""
    with get_conn() as c:
        rows = c.execute("SELECT key, value FROM settings").fetchall()
    for r in rows:
        key = r["key"]
        if key in _FIELDS:
            try:
                _apply(key, json.loads(r["value"]))
            except Exception:
                pass  # keep the default if a stored value is bad


def update(updates: dict) -> dict:
    """Validate + apply + persist a partial settings update. Raises on bad
    values (caller returns 400) so nothing half-applies to the DB."""
    applied: dict[str, object] = {}
    for key, value in updates.items():
        if key not in _FIELDS:
            continue
        _apply(key, value)  # coercion raises here on bad input
        applied[key] = _serializable(key)

    with get_conn() as c:
        for key, stored in applied.items():
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(stored)),
            )
    return get_all()
