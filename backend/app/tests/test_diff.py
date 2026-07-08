"""apply_diff SEARCH/REPLACE engine tests (Phase 8.1)."""
from __future__ import annotations

from app.services.diff import apply_blocks, parse_blocks

BLOCK = """\
<<<<<<< SEARCH
    return a + b
=======
    return a + b + 1
>>>>>>> REPLACE
"""


def test_parse_blocks():
    blocks = parse_blocks(BLOCK)
    assert len(blocks) == 1
    assert "return a + b" in blocks[0][0]
    assert "+ 1" in blocks[0][1]


def test_exact_match():
    content = "def f(a, b):\n    return a + b\n"
    blocks = parse_blocks(BLOCK)
    new, results = apply_blocks(content, blocks)
    assert results[0].ok and results[0].match_type == "exact"
    assert "return a + b + 1" in new


def test_fuzzy_whitespace_match():
    # content is LESS indented than the SEARCH block, so exact substring fails
    # but the whitespace-tolerant fuzzy match succeeds.
    content = "def f(a, b):\nreturn a + b\n"
    blocks = parse_blocks(BLOCK)
    new, results = apply_blocks(content, blocks)
    assert results[0].ok and results[0].match_type == "fuzzy"
    assert "+ 1" in new


def test_failed_match_reports_closest_region():
    content = "def f(a, b):\n    return a - b\n"  # minus, not plus
    blocks = parse_blocks(BLOCK)
    new, results = apply_blocks(content, blocks)
    assert not results[0].ok
    assert "did not match" in (results[0].error or "")
    assert "closest region" in (results[0].error or "")
    assert "return a - b" in (results[0].error or "")  # shows the near line
    assert new == content  # unchanged on failure


def test_parse_edits_and_forbidden_write():
    from app.services.pipeline import _forbidden_write, parse_edits

    text = (
        "EDIT: src/App.tsx\n"
        "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        "EDIT: main.py\n"
        "<<<<<<< SEARCH\na\n=======\nb\n>>>>>>> REPLACE\n"
    )
    edits = parse_edits(text)
    assert [p for p, _ in edits] == ["src/App.tsx", "main.py"]
    assert len(edits[0][1]) == 1  # one block for App.tsx

    assert _forbidden_write(".workbench/x") is True
    assert _forbidden_write(".workbench") is True
    assert _forbidden_write("src/App.tsx") is False


def test_multiple_blocks_sequential():
    content = "line1\nline2\nline3\n"
    text = (
        "<<<<<<< SEARCH\nline1\n=======\nLINE1\n>>>>>>> REPLACE\n"
        "<<<<<<< SEARCH\nline3\n=======\nLINE3\n>>>>>>> REPLACE\n"
    )
    new, results = apply_blocks(content, parse_blocks(text))
    assert all(r.ok for r in results)
    assert new == "LINE1\nline2\nLINE3\n"
