"""Context-condensing tests (Phase 8.6), with the LLM mocked for determinism."""
from __future__ import annotations

import pytest

from app import config
from app.services import condense, ollama


@pytest.mark.asyncio
async def test_small_thread_not_condensed():
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
    out, summary = await condense.maybe_condense(msgs, "helper")
    assert summary is None and out == msgs


@pytest.mark.asyncio
async def test_large_thread_condensed(monkeypatch):
    monkeypatch.setattr(config, "CONDENSE_CHAR_THRESHOLD", 100)
    monkeypatch.setattr(config, "CONDENSE_KEEP_RECENT", 2)

    async def fake_complete(**kwargs):
        return "- decision X\n- touched file Y", ""

    monkeypatch.setattr(ollama, "complete", fake_complete)

    msgs = [{"role": "system", "content": "SYS"}]
    for i in range(8):
        msgs.append({"role": "user", "content": f"question {i} " * 5})
        msgs.append({"role": "assistant", "content": f"answer {i} " * 5})

    out, summary = await condense.maybe_condense(msgs, "helper")
    assert summary == "- decision X\n- touched file Y"
    # system preserved, a memory block added, and the last 2 kept
    assert out[0]["content"] == "SYS"
    assert any("Condensed memory" in m["content"] for m in out)
    assert out[-1] == msgs[-1] and out[-2] == msgs[-2]
    # net shorter than the original
    assert len(out) < len(msgs)
