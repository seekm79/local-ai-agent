"""ComfyUI workflow templating tests (Phase 6)."""
from __future__ import annotations

import json

import pytest

from app import config
from app.services import comfy


def test_ship_workflow_loads_with_slots():
    wfs = comfy.list_workflows()
    assert any(w["file"] == "txt2img.json" for w in wfs)
    t2i = next(w for w in wfs if w["file"] == "txt2img.json")
    keys = {s["key"] for s in t2i["slots"]}
    assert {"positive", "negative", "seed", "steps", "width", "height"} <= keys


def test_substitute_types_and_defaults():
    tpl = comfy.load_workflow("txt2img.json")
    g = comfy.substitute(tpl, {"positive": "a red fox", "seed": 42, "width": 768})
    assert g["3"]["inputs"]["seed"] == 42
    assert isinstance(g["3"]["inputs"]["seed"], int)  # typed, not "42"
    assert g["5"]["inputs"]["width"] == 768
    assert g["6"]["inputs"]["text"] == "a red fox"
    assert g["5"]["inputs"]["height"] == 512  # default applied


def test_substitute_leaves_static_wiring():
    tpl = comfy.load_workflow("txt2img.json")
    g = comfy.substitute(tpl, {})
    # node references (lists) and constants must be preserved
    assert g["3"]["inputs"]["model"] == ["4", 0]
    assert g["3"]["inputs"]["cfg"] == 7


def test_load_workflow_rejects_traversal():
    with pytest.raises(FileNotFoundError):
        comfy.load_workflow("../../etc/passwd")


@pytest.mark.asyncio
async def test_check_online_offline_is_graceful():
    # No ComfyUI running in tests -> returns (False, message), never raises.
    online, err = await comfy.check_online()
    assert online is False
    assert err and "not detected" in err
