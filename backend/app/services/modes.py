"""Custom agent modes / personas (Phase 8.4).

A mode bundles a system prompt, an optional model + sampling params, the tools it
may use, and file-access globs. The pipeline reads its role definitions from here
(architect = planner, coder = coder, reviewer = reviewer) instead of hardcoded
prompts, and enforces allowed_tools + file_globs in code.
"""
from __future__ import annotations

import json
from fnmatch import fnmatch

from ..db import get_conn

ALL_TOOLS = ["read_file", "search_codebase", "apply_diff", "write_file",
             "run_command", "generate_image", "spawn_subtask", "browser"]

# Built-in defaults mirroring the Phase 4 roles.
_DEFAULTS = [
    {
        "slug": "architect",
        "name": "Architect",
        "system_prompt": "You are a software architect. Plan concretely; read and "
        "search code but do not modify files.",
        "allowed_tools": ["read_file", "search_codebase", "spawn_subtask"],
        "file_globs": [],
    },
    {
        "slug": "coder",
        "name": "Coder",
        "system_prompt": "You are a careful coder. Make small, anchored edits and "
        "keep the build green.",
        "allowed_tools": ["read_file", "search_codebase", "apply_diff",
                          "write_file", "run_command", "generate_image"],
        "file_globs": [],
    },
    {
        "slug": "reviewer",
        "name": "Reviewer",
        "system_prompt": "You are a reviewer. Read code and run checks/commands, but "
        "never write files.",
        "allowed_tools": ["read_file", "search_codebase", "run_command"],
        "file_globs": [],
    },
    {
        "slug": "ask",
        "name": "Ask",
        "system_prompt": "You answer questions about the project. Read-only.",
        "allowed_tools": ["read_file", "search_codebase"],
        "file_globs": [],
    },
]


def _row_to_mode(r) -> dict:
    d = dict(r)
    d["allowed_tools"] = json.loads(d.get("allowed_tools") or "[]")
    d["file_globs"] = json.loads(d.get("file_globs") or "[]")
    return d


def seed_defaults() -> None:
    with get_conn() as c:
        existing = {r["slug"] for r in c.execute("SELECT slug FROM modes")}
        for m in _DEFAULTS:
            if m["slug"] in existing:
                continue
            c.execute(
                "INSERT INTO modes (slug, name, system_prompt, allowed_tools, "
                "file_globs, built_in) VALUES (?, ?, ?, ?, ?, 1)",
                (m["slug"], m["name"], m["system_prompt"],
                 json.dumps(m["allowed_tools"]), json.dumps(m["file_globs"])),
            )


def list_modes() -> list[dict]:
    with get_conn() as c:
        rows = c.execute("SELECT * FROM modes ORDER BY built_in DESC, id ASC").fetchall()
    return [_row_to_mode(r) for r in rows]


def get_mode(slug: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT * FROM modes WHERE slug = ?", (slug,)).fetchone()
    return _row_to_mode(r) if r else None


def upsert_mode(data: dict) -> dict:
    slug = data["slug"]
    with get_conn() as c:
        c.execute(
            "INSERT INTO modes (slug, name, system_prompt, model, temperature, "
            "top_p, allowed_tools, file_globs, built_in) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET name=excluded.name, "
            "system_prompt=excluded.system_prompt, model=excluded.model, "
            "temperature=excluded.temperature, top_p=excluded.top_p, "
            "allowed_tools=excluded.allowed_tools, file_globs=excluded.file_globs",
            (slug, data.get("name", slug), data.get("system_prompt", ""),
             data.get("model"), data.get("temperature"), data.get("top_p"),
             json.dumps(data.get("allowed_tools", [])),
             json.dumps(data.get("file_globs", [])),
             int(data.get("built_in", 0))),
        )
    return get_mode(slug)  # type: ignore[return-value]


def delete_mode(slug: str) -> bool:
    with get_conn() as c:
        r = c.execute("SELECT built_in FROM modes WHERE slug = ?", (slug,)).fetchone()
        if not r or r["built_in"]:
            return False  # missing or built-in can't be deleted
        c.execute("DELETE FROM modes WHERE slug = ?", (slug,))
    return True


# --- enforcement helpers (used by the pipeline) ------------------------------
def tool_allowed(mode: dict | None, tool: str) -> bool:
    if not mode:
        return True
    return tool in mode.get("allowed_tools", ALL_TOOLS)


def path_allowed(mode: dict | None, rel_path: str) -> bool:
    if not mode:
        return True
    globs = mode.get("file_globs") or []
    if not globs:
        return True
    name = rel_path.replace("\\", "/")
    return any(fnmatch(name, g) or fnmatch(name.split("/")[-1], g) for g in globs)
