"""Shared project helpers."""
from __future__ import annotations

import re


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "project"
