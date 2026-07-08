"""Project rules / AGENTS.md (Phase 8.7 + 9.13).

On every chat and agent request we load project-level instruction files and
inject them into the system context. Canonical file is `AGENTS.md` at the
project root; a legacy `.workbench/rules.md` and a global `~/.workbench/rules.md`
are also read if present. Precedence (documented in README): explicit user
message > AGENTS.md > model defaults.
"""
from __future__ import annotations

from pathlib import Path

from .. import crud
from . import sandbox
from .sandbox import SandboxError

# Files read per project, in order.
_PROJECT_FILES = ["AGENTS.md", ".workbench/rules.md"]
_MAX_RULES_CHARS = 8000


def _read_safe(base: Path, rel: str) -> str | None:
    try:
        target = sandbox.resolve_safe(base, rel)
    except SandboxError:
        return None
    if not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8")
    except Exception:
        return None


def load_rules(project_id: int) -> str:
    """Return the concatenated rules block for a project (empty string if none)."""
    proj = crud.get_project(project_id)
    if not proj:
        return ""
    base = Path(proj["path"])
    parts: list[str] = []
    for name in _PROJECT_FILES:
        body = _read_safe(base, name)
        if body:
            parts.append(f"===== {name} =====\n{body.strip()}")

    global_rules = Path.home() / ".workbench" / "rules.md"
    if global_rules.is_file():
        try:
            parts.append(f"===== ~/.workbench/rules.md =====\n{global_rules.read_text(encoding='utf-8').strip()}")
        except Exception:
            pass

    if not parts:
        return ""
    joined = "\n\n".join(parts)[:_MAX_RULES_CHARS]
    return (
        "The user has provided project rules you MUST follow (they override your "
        "defaults; only an explicit user instruction outranks them):\n\n" + joined
    )


def has_agents_md(project_id: int) -> bool:
    proj = crud.get_project(project_id)
    if not proj:
        return False
    return (Path(proj["path"]) / "AGENTS.md").is_file()
