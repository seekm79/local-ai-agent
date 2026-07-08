-- Workbench SQLite schema. Applied on first run (and idempotent thereafter).
-- Phase 1 introduces the core tables; later phases add columns/tables here.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    slug        TEXT    NOT NULL UNIQUE,
    path        TEXT    NOT NULL,          -- absolute folder under PROJECTS_ROOT
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    title       TEXT    NOT NULL DEFAULT 'New chat',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role        TEXT    NOT NULL,          -- user | assistant | system
    content     TEXT    NOT NULL DEFAULT '',
    reasoning   TEXT,                      -- collapsed "thinking" content
    model       TEXT,
    tokens      INTEGER,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    path        TEXT    NOT NULL,          -- absolute path under project/assets
    kind        TEXT,                      -- image | video | file
    prompt      TEXT,                      -- generation prompt, if any
    workflow    TEXT,                      -- ComfyUI workflow name, if any
    params      TEXT,                      -- JSON of generation params
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    goal        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',  -- pending|running|done|failed|cancelled
    summary     TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    kind        TEXT    NOT NULL,          -- code | command | review
    title       TEXT    NOT NULL,
    detail      TEXT,
    status      TEXT    NOT NULL DEFAULT 'pending', -- pending|running|passed|failed
    output      TEXT,                      -- model output / tool calls (JSON)
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL              -- JSON-encoded value
);

-- Custom agent modes / personas (Phase 8.4).
CREATE TABLE IF NOT EXISTS modes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    system_prompt TEXT    NOT NULL DEFAULT '',
    model         TEXT,                       -- null = use the run's model
    temperature   REAL,
    top_p         REAL,
    allowed_tools TEXT    NOT NULL DEFAULT '[]',  -- JSON list
    file_globs    TEXT    NOT NULL DEFAULT '[]',  -- JSON list ([] = all files)
    built_in      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Codebase embedding index (Phase 8.3).
CREATE TABLE IF NOT EXISTS code_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    path        TEXT    NOT NULL,
    start_line  INTEGER NOT NULL,
    end_line    INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    vector      BLOB    NOT NULL,        -- packed float32
    mtime       REAL,                    -- source mtime, for incremental reindex
    UNIQUE(project_id, path, start_line)
);
CREATE INDEX IF NOT EXISTS idx_chunks_project ON code_chunks(project_id);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_steps_run ON agent_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
