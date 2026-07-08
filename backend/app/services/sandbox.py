"""Path validation + command allow/deny logic (Global rule 2 & 3).

Every file path that originates from the client or from an LLM must pass
`resolve_safe(base, relpath)` before any filesystem access. The rule:

  * resolve to an absolute real path (following symlinks),
  * verify the result stays inside the project base, which itself must live
    inside the configured projects root,
  * reject `..` traversal, absolute paths, and symlinks that escape.

Command allow/deny logic (used by the runner in Phase 3) also lives here so the
security surface is in one auditable place.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .. import config


class SandboxError(Exception):
    """Raised when a path or command violates the sandbox rules."""


def _real(p: Path) -> Path:
    # os.path.realpath resolves symlinks and normalizes, and works for paths
    # that don't exist yet (needed for create/write of new files).
    return Path(os.path.realpath(str(p)))


def projects_root() -> Path:
    return _real(config.PROJECTS_ROOT)


def _is_within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def resolve_safe(base: Path, relpath: str | None) -> Path:
    """Resolve `relpath` under `base`, guaranteeing containment.

    `base` must itself sit within the projects root. Returns the absolute real
    path. Raises SandboxError on any escape attempt.
    """
    root = projects_root()
    base_real = _real(base)
    if not _is_within(base_real, root):
        raise SandboxError("project path escapes the projects root")

    rel = "" if relpath is None else str(relpath).replace("\\", "/").strip()
    # Empty / "." means the base directory itself.
    target = _real(base_real / rel)
    if not _is_within(target, base_real):
        raise SandboxError(f"path escapes the project sandbox: {relpath!r}")
    return target


def relpath_within(base: Path, target: Path) -> str:
    """POSIX-style path of `target` relative to `base` (for API responses)."""
    rel = os.path.relpath(str(target), str(_real(base)))
    return "" if rel == "." else rel.replace("\\", "/")


# --- Command allow/deny (Global rule 3) --------------------------------------
# The command list lives in config (editable via Settings). Patterns (checked
# against the whole argv joined) are fixed here.
DENY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bgit\s+push\b.*--force", re.I),
    re.compile(r"\bcurl\b.*\|\s*sh\b", re.I),
    re.compile(r"\bwget\b.*\|\s*sh\b", re.I),
    re.compile(r"\brm\b.*-[a-z]*r", re.I),
]


def command_needs_confirmation(argv: list[str]) -> bool:
    """True if this argv must be confirmed by the user before running.

    Reads the deny-list from config live so Settings edits take effect without
    a restart."""
    if not argv:
        return False
    first = os.path.basename(argv[0]).lower()
    # Strip a .exe suffix on Windows for matching.
    first = first[:-4] if first.endswith(".exe") else first
    if first in {c.lower() for c in config.DENY_COMMANDS}:
        return True
    joined = " ".join(argv)
    return any(p.search(joined) for p in DENY_PATTERNS)
