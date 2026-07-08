"""Build-tab uploads with roles (Phase 9.10/9.11).

An attachment has a role that decides how the build uses it:
  * design_reference — palette derived from the image's dominant colors (server
    side, no vision model needed) and fed to the Designer.
  * asset — copied to public/ so the app can reference it directly.
  * content — text extracted (csv/txt/md/json/pdf) so the Builder reads the data.

Files are sandbox-validated and recorded in the `assets` table (role + derived
metadata live in the params JSON).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .. import crud
from . import sandbox

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
TEXT_EXT = {".csv", ".tsv", ".txt", ".md", ".json"}


# --- sRGB -> OKLCH -----------------------------------------------------------
def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_oklch(r: int, g: int, b: int) -> str:
    lr, lg, lb = (_srgb_to_linear(x / 255) for x in (r, g, b))
    l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb
    l_, m_, s_ = (v ** (1 / 3) if v > 0 else 0.0 for v in (l, m, s))
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = math.sqrt(a * a + bb * bb)
    H = math.degrees(math.atan2(bb, a)) % 360
    return f"oklch({L:.3f} {C:.3f} {H:.1f})"


def dominant_colors(path: Path, n: int = 5) -> list[str]:
    try:
        from PIL import Image

        img = Image.open(path).convert("RGB").resize((100, 100))
        q = img.quantize(colors=n).convert("RGB")
        counted = q.getcolors(100 * 100) or []
        counted.sort(reverse=True)
        return [rgb_to_oklch(*rgb) for _, rgb in counted[:n]]
    except Exception:
        return []


def extract_text(path: Path, budget: int = 8000) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            import pypdf

            reader = pypdf.PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)[:budget]
        if ext in TEXT_EXT:
            return path.read_text(encoding="utf-8", errors="replace")[:budget]
    except Exception:
        return ""
    return ""


# --- attachment storage ------------------------------------------------------
def _dest_rel(role: str, filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1]
    if role == "asset":
        return f"public/{name}"
    if role == "content":
        return f"uploads/{name}"
    return f"assets/references/{name}"  # design_reference


def save_attachment(project_id: int, base: Path, filename: str, data: bytes,
                    role: str) -> dict:
    rel = _dest_rel(role, filename)
    target = sandbox.resolve_safe(base, rel)  # raises on escape
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    ext = target.suffix.lower()
    kind = "image" if ext in IMAGE_EXT else "file"
    meta: dict = {"role": role}
    if role == "design_reference" and ext in IMAGE_EXT:
        meta["colors"] = dominant_colors(target)
    if role == "content":
        meta["text"] = extract_text(target)

    crud.create_asset(project_id, str(target), kind, None, role, json.dumps(meta))
    return {"path": rel, "role": role, "kind": kind,
            "colors": meta.get("colors", []), "has_text": bool(meta.get("text"))}


def list_attachments(project_id: int) -> list[dict]:
    out: list[dict] = []
    for a in crud.list_assets(project_id):
        role = None
        meta: dict = {}
        try:
            meta = json.loads(a.get("params") or "{}")
            role = meta.get("role")
        except Exception:
            pass
        if role in ("design_reference", "asset", "content"):
            out.append({
                "id": a["id"], "path": a["path"], "role": role, "kind": a["kind"],
                "colors": meta.get("colors", []),
                "text": meta.get("text", ""),
            })
    return out
