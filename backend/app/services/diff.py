"""Diff-based file editing (Phase 8.1).

The coder emits SEARCH/REPLACE blocks instead of rewriting whole files. We apply
them with an exact match first, then a whitespace-tolerant fuzzy match; on
failure we return the closest candidate region with line numbers so the model
can retry precisely.

Block format (git-merge-conflict style):

    <<<<<<< SEARCH
    original exact lines
    =======
    replacement lines
    >>>>>>> REPLACE
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

_BLOCK_RE = re.compile(
    r"<{3,}\s*SEARCH\s*\n(.*?)\n?={3,}[ \t]*\n(.*?)\n?>{3,}\s*REPLACE",
    re.S,
)


@dataclass
class BlockResult:
    ok: bool
    match_type: str  # exact | fuzzy | none
    error: str | None = None


def parse_blocks(text: str) -> list[tuple[str, str]]:
    """Extract (search, replace) pairs from model output."""
    return [(m.group(1), m.group(2)) for m in _BLOCK_RE.finditer(text)]


def _norm(line: str) -> str:
    return line.strip()


def _find_fuzzy(content_lines: list[str], search_lines: list[str]) -> int | None:
    """Return the start index of a whitespace-tolerant match, or None."""
    n = len(search_lines)
    if n == 0:
        return None
    norm_search = [_norm(s) for s in search_lines]
    for i in range(0, len(content_lines) - n + 1):
        if all(
            _norm(content_lines[i + j]) == norm_search[j] for j in range(n)
        ):
            return i
    return None


def _closest_region(content_lines: list[str], search_lines: list[str]) -> str:
    """Best-effort description of the nearest region for an error message."""
    n = len(search_lines)
    if n == 0 or not content_lines:
        return "(file is empty)"
    norm_search = [_norm(s) for s in search_lines]
    exact = 0  # count of exactly-matching normalized lines in the best window
    best_i, best_sim = 0, -1.0
    for i in range(0, max(1, len(content_lines) - n + 1)):
        sim = 0.0
        hits = 0
        for j in range(min(n, len(content_lines) - i)):
            cl = _norm(content_lines[i + j])
            sim += difflib.SequenceMatcher(None, cl, norm_search[j]).ratio()
            if cl == norm_search[j]:
                hits += 1
        if sim > best_sim:
            best_i, best_sim, exact = i, sim, hits
    end = min(best_i + n, len(content_lines))
    snippet = "\n".join(
        f"{i + 1}: {content_lines[i]}" for i in range(best_i, end)
    )
    return f"closest region (lines {best_i + 1}-{end}, {exact}/{n} lines match exactly):\n{snippet}"


def apply_blocks(
    content: str, blocks: list[tuple[str, str]]
) -> tuple[str, list[BlockResult]]:
    """Apply SEARCH/REPLACE blocks in order. Each block is applied to the result
    of the previous one. Returns (new_content, per-block results)."""
    results: list[BlockResult] = []
    for search, replace in blocks:
        # 1) exact
        if search in content:
            content = content.replace(search, replace, 1)
            results.append(BlockResult(True, "exact"))
            continue
        # 2) whitespace-tolerant fuzzy, line-based
        content_lines = content.splitlines()
        search_lines = search.splitlines()
        idx = _find_fuzzy(content_lines, search_lines)
        if idx is not None:
            new_lines = (
                content_lines[:idx]
                + replace.splitlines()
                + content_lines[idx + len(search_lines) :]
            )
            trailing = "\n" if content.endswith("\n") else ""
            content = "\n".join(new_lines) + trailing
            results.append(BlockResult(True, "fuzzy"))
            continue
        # 3) failed — return the closest candidate region
        results.append(
            BlockResult(
                False,
                "none",
                error="SEARCH block did not match. "
                + _closest_region(content_lines, search_lines),
            )
        )
    return content, results
