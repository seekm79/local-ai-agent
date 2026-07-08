"""Build-tab helper tests (Phase 9)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import config, crud
from app.services import build


def test_is_protected():
    assert build.is_protected("src/components/ui/button.tsx") is True
    assert build.is_protected("src/routeTree.gen.ts") is True
    assert build.is_protected("src/routes/index.tsx") is False
    assert build.is_protected("src/components/Dashboard.tsx") is False


STYLES = """@theme inline {\n  --color-primary: var(--primary);\n}\n
:root {
  --radius: 0.625rem;
  --background: oklch(1 0 0);
  --primary: oklch(0.2 0.04 265);
}
.dark {
  --background: oklch(0.12 0.04 264);
  --primary: oklch(0.9 0.01 255);
}
"""


def test_apply_and_read_palette(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "styles.css").write_text(STYLES, encoding="utf-8")

    build.apply_palette(tmp_path, {
        "radius": "1rem",
        "light": {"background": "oklch(0.98 0.02 90)", "primary": "oklch(0.6 0.2 30)"},
        "dark": {"background": "oklch(0.15 0.02 90)", "primary": "oklch(0.7 0.2 30)"},
    })
    pal = build.read_palette(tmp_path)
    assert pal["radius"] == "1rem"
    assert pal["light"]["primary"] == "oklch(0.6 0.2 30)"
    assert pal["dark"]["background"] == "oklch(0.15 0.02 90)"

    css = (tmp_path / "src" / "styles.css").read_text(encoding="utf-8")
    assert "@theme inline" in css  # @theme block preserved


def test_partial_palette_merges(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "styles.css").write_text(STYLES, encoding="utf-8")
    # change ONLY primary — background must be preserved, not dropped
    build.apply_palette(tmp_path, {"light": {"primary": "oklch(0.6 0.2 30)"}})
    pal = build.read_palette(tmp_path)
    assert pal["light"]["primary"] == "oklch(0.6 0.2 30)"
    assert pal["light"]["background"] == "oklch(1 0 0)"  # preserved


def test_scaffold_copies_template(tmp_path, monkeypatch):
    if not build.template_available():
        pytest.skip("web template not present")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "ws")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "b.db")
    from app.db import init_db

    init_db()
    proj = build.scaffold("My Dash", "A finance dashboard")
    base = Path(proj["path"])
    assert (base / "package.json").is_file()
    assert (base / "src" / "components" / "ui" / "button.tsx").is_file()
    assert "A finance dashboard" in (base / "AGENTS.md").read_text(encoding="utf-8")
    assert crud.get_project(proj["id"]) is not None
