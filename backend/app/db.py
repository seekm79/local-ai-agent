"""SQLite initialization and helpers.

The DB is created from schema.sql on first run. schema.sql is idempotent
(CREATE TABLE IF NOT EXISTS), so applying it on every startup is safe.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create the DB file and apply schema.sql. Called once on startup."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = config.SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.executescript(schema)
        conn.commit()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Context-managed connection with commit/rollback handling."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
