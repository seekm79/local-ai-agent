"""Build tab support (Phase 9): scaffold from the fixed template, apply oklch
palettes to src/styles.css, and enforce the "do not touch" protections.

The heavy orchestration (Designer -> Builder -> Fixer) lives in the pipeline,
reusing the Phase 4/8 coder machinery. This module holds the non-LLM helpers.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .. import config, crud
from .projects_util import slugify

# The design tokens the Designer may rewrite (light + dark). @theme is off-limits.
PALETTE_TOKENS = [
    "background", "foreground", "card", "card-foreground", "popover",
    "popover-foreground", "primary", "primary-foreground", "secondary",
    "secondary-foreground", "muted", "muted-foreground", "accent",
    "accent-foreground", "destructive", "destructive-foreground", "border",
    "input", "ring", "chart-1", "chart-2", "chart-3", "chart-4", "chart-5",
    "sidebar", "sidebar-foreground", "sidebar-primary", "sidebar-primary-foreground",
    "sidebar-accent", "sidebar-accent-foreground", "sidebar-border", "sidebar-ring",
]

# Core tokens the Designer is asked to set (the rest are preserved by
# apply_palette, keeping the LLM's output small and fast).
CORE_TOKENS = [
    "background", "foreground", "card", "card-foreground", "primary",
    "primary-foreground", "secondary", "secondary-foreground", "muted",
    "muted-foreground", "accent", "accent-foreground", "border", "input", "ring",
    "sidebar", "sidebar-foreground", "sidebar-primary", "sidebar-accent",
]


def template_available() -> bool:
    return (config.WEBAPP_TEMPLATE_DIR / "package.json").is_file()


def is_protected(rel: str) -> bool:
    """Files the agent must never modify/delete (9.5)."""
    n = rel.replace("\\", "/").lstrip("/")
    return (
        n.startswith("src/components/ui/")
        or n == "src/routeTree.gen.ts"
        or n == "src/components/ui"
    )


# Instruction/filler words that shouldn't become a project name on their own.
_NAME_STOP = {
    "a", "an", "the", "and", "or", "of", "for", "to", "with", "please", "read",
    "attached", "ai", "prompt", "carefully", "careful", "before", "after", "build",
    "building", "builds", "create", "creating", "make", "making", "me", "my", "app",
    "application", "start", "starting", "generate", "generating", "require",
    "requires", "required", "plan", "planning", "then", "using", "use", "that",
    "this", "it", "is", "are", "be", "in", "on", "as", "by",
}


def _titlecase(text: str) -> str:
    """Title-case a name while preserving short all-caps acronyms (CRM, API, SaaS)."""
    out = []
    for w in text.split():
        if w.isupper() and len(w) <= 4:
            out.append(w)                      # keep acronyms as-is
        elif w.isalpha():
            out.append(w[:1].upper() + w[1:].lower())
        else:
            out.append(w)                      # punctuation, mixed tokens
    return " ".join(out)


def name_from_prompt(prompt: str) -> str:
    """Derive a readable project name from a build prompt WITHOUT an LLM.

    Prefers a short title-like first line (e.g. "CRM - Helpdesk"); otherwise drops
    instruction/filler words and keeps the first few meaningful ones. This is the
    instant fallback for the LLM namer (routers/build._suggest_name)."""
    text = (prompt or "").strip()
    if not text:
        return "app"
    first = text.splitlines()[0].strip(" -–—:#*\t").strip()
    if 2 <= len(first) <= 40 and len(first.split()) <= 6:
        return _titlecase(first)
    words = re.findall(r"[A-Za-z0-9]+", text)
    kept = [w for w in words if w.lower() not in _NAME_STOP][:4]
    return _titlecase(" ".join(kept)) or "app"


def clean_name(raw: str) -> str:
    """Sanitize a model-produced name: last non-empty line, strip quotes/labels,
    cap length. Returns "" if it doesn't look like a name (too long/empty)."""
    line = next((ln.strip() for ln in reversed((raw or "").splitlines()) if ln.strip()), "")
    line = re.sub(r'^["\'`*#\s-]+|["\'`*\s]+$', "", line)
    line = line.split(":")[-1].strip()         # drop a "Project name:" label
    words = line.split()
    if not words or len(words) > 8:
        return ""
    return _titlecase(" ".join(words[:5]))[:48]


def scaffold(name: str, overview: str) -> dict:
    """Copy the template into workspace/<slug>/ and fill AGENTS.md. Returns the
    project row. Dependency install happens separately (it's slow + streamed)."""
    base_slug = slugify(name)
    slug, i = base_slug, 2
    while crud.slug_exists(slug):
        slug, i = f"{base_slug}-{i}", i + 1

    dest = (config.PROJECTS_ROOT / slug).resolve()
    # Never copy node_modules or build artifacts from the template: copying a
    # node_modules breaks its .bin symlinks (e.g. .bin/vite → a dangling path),
    # so Vite can't launch and EVERY build check fails regardless of the code the
    # Builder writes. Excluding them lets the post-scaffold `bun install` produce
    # a correct, fresh install. (.git/.output/dist/.wrangler are just noise.)
    _skip = shutil.ignore_patterns("node_modules", ".output", "dist",
                                   ".wrangler", ".git", ".workbench")
    shutil.copytree(config.WEBAPP_TEMPLATE_DIR, dest, dirs_exist_ok=True, ignore=_skip)
    (dest / "assets").mkdir(exist_ok=True)
    (dest / "public").mkdir(exist_ok=True)

    _fill_agents_md(dest, overview)
    return crud.create_project(name, slug, str(dest))


def _fill_agents_md(dest: Path, overview: str) -> None:
    agents = dest / "AGENTS.md"
    if not agents.is_file():
        return
    text = agents.read_text(encoding="utf-8")
    text = text.replace(
        "A web application scaffolded from the fixed base template.",
        overview.strip() or "A web application scaffolded from the fixed base template.",
    )
    agents.write_text(text, encoding="utf-8")


# --- oklch palette application (9.6) -----------------------------------------
_ROOT_RE = re.compile(r"(:root\s*\{)([^}]*)(\})", re.S)
_DARK_RE = re.compile(r"(\.dark\s*\{)([^}]*)(\})", re.S)
_OKLCH_RE = re.compile(r"^oklch\(", re.I)


def _render_block(values: dict, include_radius: bool) -> str:
    lines = []
    if include_radius:
        lines.append(f"  --radius: {values.get('radius', '0.625rem')};")
    for token in PALETTE_TOKENS:
        val = values.get(token)
        if val:
            lines.append(f"  --{token}: {val};")
    return "\n" + "\n".join(lines) + "\n"


def apply_palette(base: Path, palette: dict) -> None:
    """Rewrite the :root and .dark token *values* in src/styles.css, MERGING the
    provided tokens over the existing ones (a partial palette only changes the
    tokens it names). Preserves the @theme block and everything else."""
    styles = base / "src" / "styles.css"
    css = styles.read_text(encoding="utf-8")

    # Start from the current values so a partial update doesn't drop tokens.
    current = read_palette(base)
    light = {**current.get("light", {}), **palette.get("light", {})}
    dark = {**current.get("dark", {}), **palette.get("dark", {})}
    if "radius" in palette:
        light = {**light, "radius": palette["radius"]}

    css = _ROOT_RE.sub(
        lambda m: m.group(1) + _render_block(light, include_radius=True) + m.group(3),
        css,
        count=1,
    )
    css = _DARK_RE.sub(
        lambda m: m.group(1) + _render_block(dark, include_radius=False) + m.group(3),
        css,
        count=1,
    )
    styles.write_text(css, encoding="utf-8")


def _parse_block(block: str) -> dict:
    out: dict = {}
    for m in re.finditer(r"--([\w-]+):\s*([^;]+);", block):
        out[m.group(1)] = m.group(2).strip()
    return out


def read_palette(base: Path) -> dict:
    """Read the current :root/.dark token values from src/styles.css."""
    styles = base / "src" / "styles.css"
    if not styles.is_file():
        return {"radius": "0.625rem", "light": {}, "dark": {}}
    css = styles.read_text(encoding="utf-8")
    root = _ROOT_RE.search(css)
    dark = _DARK_RE.search(css)
    light_vals = _parse_block(root.group(2)) if root else {}
    dark_vals = _parse_block(dark.group(2)) if dark else {}
    radius = light_vals.pop("radius", "0.625rem")
    dark_vals.pop("radius", None)
    return {"radius": radius, "light": light_vals, "dark": dark_vals}


def install_command() -> list[str]:
    return [config.WEB_PACKAGE_MANAGER, "install"]


def dev_command() -> list[str]:
    return [config.WEB_PACKAGE_MANAGER, "run", "dev"]


def build_command() -> list[str]:
    return [config.WEB_PACKAGE_MANAGER, "run", "build"]
