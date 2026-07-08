"""Codebase indexing + semantic search (Phase 8.3).

Chunks source files, embeds them with a local Ollama embedding model, stores
vectors in SQLite, and answers `search_codebase(query, top_k)` via cosine
similarity. Re-indexing is incremental (only files whose mtime changed). No
external vector DB — pure-Python cosine is plenty for local project sizes.
"""
from __future__ import annotations

import math
import os
import struct
from pathlib import Path

import httpx

from .. import config
from ..db import get_conn

# Source extensions we index (skip binaries, media, lockfiles).
_CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".dart", ".gd", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".css", ".scss",
    ".html", ".md", ".json", ".yaml", ".yml", ".sql", ".sh", ".toml",
}
_SKIP_DIRS = {"node_modules", ".git", ".workbench", "obj", "bin", "dist", ".vs",
              "__pycache__", ".venv", "venv"}
# Generated/lock files: indexed content is noise and huge.
_SKIP_NAMES = {"package-lock.json", "bun.lock", "bun.lockb", "yarn.lock",
               "pnpm-lock.yaml", "poetry.lock", "routeTree.gen.ts"}
_CHUNK_LINES = 50
_CHUNK_OVERLAP = 10
_MAX_FILE_BYTES = 400_000


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts via Ollama's OpenAI-compatible /v1/embeddings."""
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/embeddings"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json={"model": config.MODEL_EMBED, "input": texts})
        resp.raise_for_status()
        data = resp.json()
    return [item["embedding"] for item in data["data"]]


async def available() -> tuple[bool, str | None]:
    try:
        await embed(["ping"])
        return True, None
    except Exception as exc:
        return False, (
            f"Embedding model '{config.MODEL_EMBED}' not available "
            f"({type(exc).__name__}). Pull it: `ollama pull {config.MODEL_EMBED}`."
        )


def _chunk(text: str) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    out: list[tuple[int, int, str]] = []
    i = 0
    n = len(lines)
    if n == 0:
        return out
    step = max(1, _CHUNK_LINES - _CHUNK_OVERLAP)
    while i < n:
        chunk_lines = lines[i : i + _CHUNK_LINES]
        body = "\n".join(chunk_lines).strip()
        if body:
            out.append((i + 1, min(i + _CHUNK_LINES, n), body))
        i += step
    return out


def _iter_source_files(base: Path):
    # os.walk with in-place dirname pruning so we never descend into
    # node_modules/.git/etc. (rglob would enumerate them all first — very slow).
    for root, dirs, filenames in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in sorted(filenames):
            if name in _SKIP_NAMES or name.endswith(".lock"):
                continue
            p = Path(root) / name
            if p.suffix.lower() not in _CODE_EXT:
                continue
            try:
                if p.stat().st_size <= _MAX_FILE_BYTES:
                    yield p
            except OSError:
                continue


async def index_project(project_id: int, base: Path, force: bool = False) -> dict:
    """(Re)index changed files. Returns {files, chunks, skipped}."""
    with get_conn() as c:
        rows = c.execute(
            "SELECT path, mtime FROM code_chunks WHERE project_id = ? GROUP BY path",
            (project_id,),
        ).fetchall()
        known = {r["path"]: r["mtime"] for r in rows}

    indexed_files = 0
    total_chunks = 0
    seen_paths: set[str] = set()
    for p in _iter_source_files(base):
        rel = p.relative_to(base).as_posix()
        seen_paths.add(rel)
        mtime = p.stat().st_mtime
        if not force and known.get(rel) == mtime:
            continue  # unchanged
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        chunks = _chunk(text)
        if not chunks:
            continue
        vectors = await embed([f"{rel}\n{body}" for _, _, body in chunks])
        with get_conn() as c:
            c.execute(
                "DELETE FROM code_chunks WHERE project_id = ? AND path = ?",
                (project_id, rel),
            )
            for (start, end, body), vec in zip(chunks, vectors):
                c.execute(
                    "INSERT OR REPLACE INTO code_chunks "
                    "(project_id, path, start_line, end_line, text, vector, mtime) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (project_id, rel, start, end, body, _pack(vec), mtime),
                )
        indexed_files += 1
        total_chunks += len(chunks)

    # Drop chunks for files that no longer exist.
    stale = set(known) - seen_paths
    if stale:
        with get_conn() as c:
            for rel in stale:
                c.execute(
                    "DELETE FROM code_chunks WHERE project_id = ? AND path = ?",
                    (project_id, rel),
                )

    return {"files": indexed_files, "chunks": total_chunks, "removed": len(stale)}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def search(project_id: int, query: str, top_k: int = 6) -> list[dict]:
    qvec = (await embed([query]))[0]
    with get_conn() as c:
        rows = c.execute(
            "SELECT path, start_line, end_line, text, vector FROM code_chunks "
            "WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    scored = [
        {
            "path": r["path"],
            "start_line": r["start_line"],
            "end_line": r["end_line"],
            "text": r["text"],
            "score": _cosine(qvec, _unpack(r["vector"])),
        }
        for r in rows
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def chunk_count(project_id: int) -> int:
    with get_conn() as c:
        r = c.execute(
            "SELECT COUNT(*) AS n FROM code_chunks WHERE project_id = ?", (project_id,)
        ).fetchone()
    return r["n"]
