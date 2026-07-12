"""Phase 10 — agentic worker loop / orchestrator unit tests.

These cover the pure parsing + write-application logic without touching Ollama;
the loop and orchestrator themselves are integration-level (need a live model).
"""
from __future__ import annotations

import asyncio

import pytest

from app import config
from app.services import agentic


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project dir under a patched PROJECTS_ROOT so sandbox.resolve_safe accepts it."""
    root = tmp_path / "workspace"
    proj = root / "app"
    proj.mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECTS_ROOT", root)
    return proj


def test_parse_action_json_fenced():
    a = agentic.parse_action(
        'Let me look.\n```json\n{"tool": "read_file", "path": "src/App.tsx"}\n```')
    assert a == {"tool": "read_file", "path": "src/App.tsx"}


def test_parse_action_bare_json():
    assert agentic.parse_action('{"tool": "finish", "summary": "done"}') == {
        "tool": "finish", "summary": "done"}


def test_parse_action_run_command():
    a = agentic.parse_action('{"tool": "run_command", "argv": ["npm", "install"]}')
    assert a["tool"] == "run_command" and a["argv"] == ["npm", "install"]


def test_write_turn_is_not_an_action():
    # A FILE:/EDIT: turn must NOT be mistaken for a control action.
    content = "FILE: src/x.ts\n```\nexport const a = {x: 1};\n```"
    assert agentic.parse_action(content) is None


def test_unknown_tool_rejected():
    assert agentic.parse_action('{"tool": "delete_everything"}') is None
    assert agentic.parse_action("no json here at all") is None


def test_apply_writes_creates_file(project):
    events: list[tuple[str, dict]] = []
    emit = lambda t, p: events.append((t, p))  # noqa: E731
    log: dict = {"messages": [], "tools": []}
    content = "FILE: src/hello.ts\n```\nexport const hi = () => 'hi';\n```"
    wrote, feedback = asyncio.run(
        agentic._apply_writes(emit, 1, 1, project, content, None, log))
    assert wrote is True
    assert feedback == ""
    assert (project / "src" / "hello.ts").read_text().startswith("export const hi")
    assert any(t == "tool_result" and p.get("ok") for t, p in events)


def test_apply_writes_refuses_protected(project):
    events: list[tuple[str, dict]] = []
    emit = lambda t, p: events.append((t, p))  # noqa: E731
    log: dict = {"messages": [], "tools": []}
    # .workbench/ is reserved checkpoint infra — writes must be refused.
    content = "FILE: .workbench/evil.txt\n```\npwned\n```"
    wrote, feedback = asyncio.run(
        agentic._apply_writes(emit, 1, 1, project, content, None, log))
    assert wrote is False
    assert "protected" in feedback
    assert not (project / ".workbench" / "evil.txt").exists()


def test_trim_keeps_head_and_tail():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"}]
    msgs += [{"role": "assistant", "content": f"m{i}"} for i in range(20)]
    trimmed = agentic._trim(msgs, keep_recent=8)
    assert trimmed[0]["content"] == "s"
    assert trimmed[1]["content"] == "task"
    assert trimmed[-1]["content"] == "m19"
    assert any("omitted" in m["content"] for m in trimmed)
    assert len(trimmed) < len(msgs)
