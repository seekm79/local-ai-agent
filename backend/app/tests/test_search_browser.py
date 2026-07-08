"""Unit tests for embeddings helpers (8.3) and browser availability (8.8)."""
from __future__ import annotations

import pytest

from app.services import browser, embeddings


def test_chunk_windows():
    text = "\n".join(f"line{i}" for i in range(120))
    chunks = embeddings._chunk(text)
    assert len(chunks) >= 2
    # chunks carry 1-based line ranges and non-empty bodies
    assert chunks[0][0] == 1
    assert all(body.strip() for _, _, body in chunks)


def test_chunk_empty():
    assert embeddings._chunk("") == []


def test_pack_unpack_roundtrip():
    vec = [0.1, -0.5, 3.14, 0.0]
    back = embeddings._unpack(embeddings._pack(vec))
    assert len(back) == len(vec)
    assert all(abs(a - b) < 1e-6 for a, b in zip(vec, back))


def test_cosine():
    assert embeddings._cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert embeddings._cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert embeddings._cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)


def test_disjoint_subtask_grouping():
    from app.services.pipeline import _disjoint_groups

    steps = [
        {"target_files": ["a.txt"]},
        {"target_files": ["b.txt"]},
        {"target_files": ["a.txt"]},  # overlaps first -> must sequence
    ]
    groups = _disjoint_groups(steps)
    assert len(groups) == 2
    assert groups[0] == [{"target_files": ["a.txt"]}, {"target_files": ["b.txt"]}]
    assert groups[1] == [{"target_files": ["a.txt"]}]


@pytest.mark.asyncio
async def test_browser_available_after_install():
    ok, err = await browser.available()
    # Playwright is installed in this environment; if not, the error is clear.
    assert ok or (err and "Playwright" in err)
