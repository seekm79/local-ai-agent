"""Small data-access helpers over SQLite. Kept ORM-free per the spec.

Returned rows are plain dicts so routers can serialize them directly.
"""
from __future__ import annotations

from typing import Any

from .db import get_conn


def _row(r: Any) -> dict:
    return dict(r) if r is not None else {}


# --- Projects ----------------------------------------------------------------
def list_projects(include_archived: bool = False) -> list[dict]:
    q = (
        "SELECT id, name, slug, path, archived, created_at FROM projects "
        + ("" if include_archived else "WHERE archived = 0 ")
        + "ORDER BY id DESC"
    )
    with get_conn() as c:
        rows = c.execute(q).fetchall()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute(
            "SELECT id, name, slug, path, archived, created_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def slug_exists(slug: str) -> bool:
    with get_conn() as c:
        row = c.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone()
    return row is not None


def create_project(name: str, slug: str, path: str) -> dict:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO projects (name, slug, path) VALUES (?, ?, ?)",
            (name, slug, path),
        )
        pid = cur.lastrowid
        row = c.execute(
            "SELECT id, name, slug, path, archived, created_at FROM projects WHERE id = ?",
            (pid,),
        ).fetchone()
    return _row(row)


def archive_project(project_id: int) -> None:
    with get_conn() as c:
        c.execute("UPDATE projects SET archived = 1 WHERE id = ?", (project_id,))


def delete_project_row(project_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM projects WHERE id = ?", (project_id,))


# --- Assets ------------------------------------------------------------------
def create_asset(
    project_id: int,
    path: str,
    kind: str,
    prompt: str | None = None,
    workflow: str | None = None,
    params: str | None = None,
) -> dict:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO assets (project_id, path, kind, prompt, workflow, params) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, path, kind, prompt, workflow, params),
        )
        aid = cur.lastrowid
        row = c.execute("SELECT * FROM assets WHERE id = ?", (aid,)).fetchone()
    return dict(row)


def list_assets(project_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM assets WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_asset(asset_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return dict(row) if row else None


def delete_asset(asset_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def update_asset_params(asset_id: int, params: str) -> None:
    with get_conn() as c:
        c.execute("UPDATE assets SET params = ? WHERE id = ?", (params, asset_id))


# --- Chats -------------------------------------------------------------------
def list_chats() -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT id, project_id, title, created_at FROM chats ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_chat(title: str = "New chat", project_id: int | None = None) -> dict:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO chats (title, project_id) VALUES (?, ?)", (title, project_id)
        )
        cid = cur.lastrowid
        row = c.execute(
            "SELECT id, project_id, title, created_at FROM chats WHERE id = ?", (cid,)
        ).fetchone()
    return _row(row)


def get_chat(chat_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute(
            "SELECT id, project_id, title, created_at FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
    return dict(row) if row else None


def rename_chat(chat_id: int, title: str) -> None:
    with get_conn() as c:
        c.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))


def delete_chat(chat_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


# --- Messages ----------------------------------------------------------------
def list_messages(chat_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT id, chat_id, role, content, reasoning, model, tokens, created_at "
            "FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(
    chat_id: int,
    role: str,
    content: str = "",
    reasoning: str | None = None,
    model: str | None = None,
    tokens: int | None = None,
) -> dict:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO messages (chat_id, role, content, reasoning, model, tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, role, content, reasoning, model, tokens),
        )
        mid = cur.lastrowid
        row = c.execute(
            "SELECT id, chat_id, role, content, reasoning, model, tokens, created_at "
            "FROM messages WHERE id = ?",
            (mid,),
        ).fetchone()
    return _row(row)


def update_message(
    message_id: int,
    content: str,
    reasoning: str | None = None,
    tokens: int | None = None,
) -> None:
    with get_conn() as c:
        c.execute(
            "UPDATE messages SET content = ?, reasoning = ?, tokens = ? WHERE id = ?",
            (content, reasoning, tokens, message_id),
        )


def delete_message(message_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM messages WHERE id = ?", (message_id,))


def delete_messages_from(chat_id: int, message_id: int) -> None:
    """Delete the given message and everything after it in the chat."""
    with get_conn() as c:
        c.execute(
            "DELETE FROM messages WHERE chat_id = ? AND id >= ?", (chat_id, message_id)
        )


def get_message(message_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute(
            "SELECT id, chat_id, role, content, reasoning, model, tokens, created_at "
            "FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
    return dict(row) if row else None


def last_message(chat_id: int, role: str) -> dict | None:
    with get_conn() as c:
        row = c.execute(
            "SELECT id, chat_id, role, content, reasoning, model, tokens, created_at "
            "FROM messages WHERE chat_id = ? AND role = ? ORDER BY id DESC LIMIT 1",
            (chat_id, role),
        ).fetchone()
    return dict(row) if row else None


# --- Agent runs / steps (Phase 4) -------------------------------------------
def create_run(project_id: int, goal: str) -> dict:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO agent_runs (project_id, goal, status) VALUES (?, ?, 'pending')",
            (project_id, goal),
        )
        rid = cur.lastrowid
        row = c.execute("SELECT * FROM agent_runs WHERE id = ?", (rid,)).fetchone()
    return dict(row)


def update_run(run_id: int, status: str, summary: str | None = None) -> None:
    with get_conn() as c:
        c.execute(
            "UPDATE agent_runs SET status = ?, summary = COALESCE(?, summary) WHERE id = ?",
            (status, summary, run_id),
        )


def reset_orphaned_runs() -> int:
    """Mark runs left mid-flight by a previous process as interrupted. A run in
    'running'/'pending'/'waiting' has no live pipeline task after a restart, so
    it would otherwise show as perpetually 'running' in the UI. Returns count."""
    with get_conn() as c:
        cur = c.execute(
            "UPDATE agent_runs SET status = 'interrupted', "
            "summary = COALESCE(summary, 'Interrupted — the server restarted while "
            "this run was in progress.') "
            "WHERE status IN ('running', 'pending', 'waiting')"
        )
        # In-progress steps are dead too; surface them as failed for clarity.
        c.execute("UPDATE agent_steps SET status = 'failed' WHERE status = 'running'")
        return cur.rowcount


def list_runs() -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT id, project_id, goal, status, summary, created_at "
            "FROM agent_runs ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def create_step(
    run_id: int, idx: int, kind: str, title: str, detail: str | None
) -> dict:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO agent_steps (run_id, idx, kind, title, detail, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (run_id, idx, kind, title, detail),
        )
        sid = cur.lastrowid
        row = c.execute("SELECT * FROM agent_steps WHERE id = ?", (sid,)).fetchone()
    return dict(row)


def update_step(step_id: int, status: str, output: str | None = None) -> None:
    with get_conn() as c:
        c.execute(
            "UPDATE agent_steps SET status = ?, output = COALESCE(?, output) WHERE id = ?",
            (status, output, step_id),
        )


def list_steps(run_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM agent_steps WHERE run_id = ? ORDER BY idx ASC", (run_id,)
        ).fetchall()
    return [dict(r) for r in rows]
