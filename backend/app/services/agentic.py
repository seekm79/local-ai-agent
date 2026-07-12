"""Agentic worker loop + orchestrator (Phase 10 — Roo-Code-style autonomy).

The Phase-4 pipeline is *plan-once, single-shot-per-step*: a great fit for small
goals, but it can't build a large multi-module app — the planner is capped at a
handful of steps and the coder never gets to read a file it wasn't handed. This
module adds the two pieces a real agentic coder needs:

  1. ``run_worker`` — a genuine ReAct loop. The worker model repeatedly emits ONE
     action, we execute it, feed back an OBSERVATION, and continue until it calls
     ``finish`` (gated on a green build) or exhausts its step budget. It can
     ``read_file`` / ``list_files`` / ``search_codebase`` to pull the context it
     needs, then ``write_file`` / ``apply_diff`` to change code, and
     ``run_command`` / ``run_check`` to verify.
  2. ``decompose`` — an orchestrator that turns a big goal into an ordered backlog
     of self-contained, independently-buildable tasks. ``Pipeline`` runs each task
     through ``run_worker`` with a checkpoint between them.

Protocol note: Ollama's OpenAI shim has no native tool-calling, so the protocol
is text-based — control actions are a single fenced JSON object, while file
writes stay as the existing ``FILE:``/``EDIT:`` fenced blocks (embedding code in
a JSON string is brittle with weak local models; the rest of this codebase
already learned that). ``run_worker`` emits the same ``model_message`` /
``tool_call`` / ``tool_result`` / ``step_update`` events the Phase-4 board
already renders, so the loop visualizes with no frontend changes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Awaitable, Callable

from .. import config, crud
from . import build, checkpoints, diff, embeddings, modes, ollama, runner, sandbox
from .sandbox import SandboxError

Emit = Callable[[str, dict], None]


# --- Tool protocol -----------------------------------------------------------
WORKER_SYSTEM = """You are an autonomous CODER agent working in a real project. \
You operate in a LOOP: each turn you take exactly ONE action, then you receive an \
OBSERVATION with the result, and you continue until the task is complete.

To inspect the project, emit ONE fenced JSON object and nothing else:
```json
{"tool": "read_file", "path": "src/App.tsx"}
```
Available inspection/command tools (one per turn):
- {"tool": "read_file", "path": "<relative path>"}          read a file's contents
- {"tool": "list_files", "path": "<relative dir or omit>"}  list the file tree
- {"tool": "search_codebase", "query": "<what you need>"}   semantic code search
- {"tool": "run_command", "argv": ["npm", "install", "zod"]} run a shell command
- {"tool": "run_check"}                                       run the project build/check
- {"tool": "finish", "summary": "<what you did>"}            end the task (only when done)

To CHANGE code, do NOT use JSON — emit one or more of these blocks instead:
EDIT an existing file (SEARCH must copy the CURRENT lines EXACTLY):
EDIT: <relative/path>
<<<<<<< SEARCH
<exact current lines>
=======
<new lines>
>>>>>>> REPLACE
CREATE a new file with its full contents:
FILE: <relative/path>
```
<full file contents>
```

Rules:
- Take ONE action per turn. Read/search before you edit a file you haven't seen.
- NEVER assume the project's framework or that a file exists. Use list_files and
  read_file to confirm the real structure before editing. Do not invent files like
  src/App.tsx unless list_files shows them.
- Only create or edit the files THIS task calls for — nothing extra.
- After you write files the harness auto-runs the build and reports errors — fix them.
- Use EDIT for files that already exist, FILE only for brand-new files.
- Call finish as soon as the task's deliverables exist and the build (if any) is
  green. If the task is just to read/inspect, finish right after reporting what you
  found. Do not keep looping once the work is done.
- Never explain outside of an action; every turn is either JSON, or FILE:/EDIT: blocks."""


def parse_action(content: str) -> dict | None:
    """Extract a single control-action JSON object from a worker turn.

    Returns the dict when it names a known ``tool`` and carries no file-write
    payload; otherwise None (the turn is then treated as writes or a nudge)."""
    from .pipeline import extract_json  # lazy: avoid import cycle with pipeline

    try:
        data = extract_json(content)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    tool = data.get("tool")
    if tool in {"read_file", "list_files", "search_codebase", "run_command",
                "run_check", "finish"}:
        return data
    return None


# --- Write application (guards mirror pipeline._code, kept independent) -------
async def _apply_writes(
    emit: Emit, run_id: int, step_id: int, base: Path, content: str,
    mode: dict | None, log: dict,
) -> tuple[bool, str]:
    """Apply the EDIT/FILE blocks in a worker turn. Returns (any_written,
    feedback) where feedback lists per-block failures to feed back to the model."""
    from .pipeline import (_clean_path, _forbidden_write, _is_binary_path,
                           parse_coder, parse_edits)

    edits = parse_edits(content)
    edited = {p for p, _ in edits}
    files, _cmds = parse_coder(content, targets=[])
    files = [f for f in files if _clean_path(f.get("path", "")) not in edited]

    feedback: list[str] = []
    wrote = False

    def _guarded(path: str, tool: str) -> str | None:
        """Return a refusal reason, or None if the write is allowed."""
        if _forbidden_write(path) or build.is_protected(path):
            return f"{path} is protected (ui/, generated files, or .workbench/)"
        if _is_binary_path(path):
            return f"{path} is a binary asset — never write it as text"
        if not modes.tool_allowed(mode, tool):
            return f"{tool} not allowed in this mode"
        if not modes.path_allowed(mode, path):
            return f"{path} is outside this mode's allowed file globs"
        return None

    for path, blocks in edits:
        emit("tool_call", {"run_id": run_id, "step_id": step_id, "tool": "apply_diff",
                           "args": {"path": path, "blocks": len(blocks)}})
        reason = _guarded(path, "apply_diff")
        if reason:
            emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": "apply_diff",
                                 "ok": False, "output": f"refused: {reason}"})
            feedback.append(reason)
            continue
        try:
            target = sandbox.resolve_safe(base, path)
        except SandboxError as e:
            emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": "apply_diff",
                                 "ok": False, "output": f"blocked: {e}"})
            feedback.append(f"{path}: blocked ({e})")
            continue
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        after, results = diff.apply_blocks(before, blocks)
        failed = [r for r in results if not r.ok]
        if failed:
            errtext = " | ".join(r.error or "match failed" for r in failed)
            emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": "apply_diff",
                                 "ok": False, "output": errtext})
            feedback.append(f"apply_diff on {path} failed: {errtext}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(after, encoding="utf-8")
        wrote = True
        log["tools"].append({"tool": "apply_diff", "path": path, "ok": True})
        emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": "apply_diff",
                             "ok": True, "output": f"{path}: applied {len(blocks)} block(s)",
                             "path": path, "before": before, "after": after})

    for f in files:
        path, body = _clean_path(f.get("path", "")), f.get("content", "")
        if not path:
            continue
        emit("tool_call", {"run_id": run_id, "step_id": step_id, "tool": "write_file",
                           "args": {"path": path}})
        reason = _guarded(path, "write_file")
        if reason:
            emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": "write_file",
                                 "ok": False, "output": f"refused: {reason}"})
            feedback.append(reason)
            continue
        try:
            target = sandbox.resolve_safe(base, path)
            before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            wrote = True
            log["tools"].append({"tool": "write_file", "path": path, "ok": True})
            emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": "write_file",
                                 "ok": True, "output": f"{path}: wrote {len(body)} bytes",
                                 "path": path, "before": before, "after": body})
        except (SandboxError, OSError) as e:
            emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": "write_file",
                                 "ok": False, "output": f"failed: {e}"})
            feedback.append(f"{path}: write failed ({e})")

    return wrote, "\n".join(feedback)


# --- Control tools -----------------------------------------------------------
async def _exec_control(
    emit: Emit, run_id: int, step_id: int, project_id: int, base: Path,
    mode: dict | None, action: dict, log: dict,
) -> str:
    """Execute one non-write control tool and return its OBSERVATION text."""
    from .pipeline import _clip_error, _file_tree, _read_safe, check_command

    tool = action["tool"]
    emit("tool_call", {"run_id": run_id, "step_id": step_id, "tool": tool,
                       "args": {k: v for k, v in action.items() if k != "tool"}})

    def _result(ok: bool, output: str) -> str:
        log["tools"].append({"tool": tool, "ok": ok})
        emit("tool_result", {"run_id": run_id, "step_id": step_id, "tool": tool,
                             "ok": ok, "output": output[:800]})
        return output

    if tool == "read_file":
        path = str(action.get("path", "")).strip()
        if not modes.tool_allowed(mode, "read_file"):
            return _result(False, "read_file not allowed in this mode")
        text = _read_safe(base, path, budget=8000)
        if not text:
            return _result(False, f"{path}: not found or empty")
        return _result(True, f"--- {path} ---\n{text}")

    if tool == "list_files":
        sub = str(action.get("path", "")).strip().strip("/")
        root = base
        if sub:
            try:
                root = sandbox.resolve_safe(base, sub)
            except SandboxError as e:
                return _result(False, f"blocked: {e}")
        if not root.is_dir():
            return _result(False, f"{sub or '.'}: not a directory")
        return _result(True, _file_tree(root, limit=200))

    if tool == "search_codebase":
        query = str(action.get("query", "")).strip()
        if not modes.tool_allowed(mode, "search_codebase"):
            return _result(False, "search_codebase not allowed in this mode")
        if embeddings.chunk_count(project_id) == 0:
            return _result(False, "no codebase index yet — use list_files/read_file")
        try:
            hits = await embeddings.search(project_id, query, top_k=5)
        except Exception as e:
            return _result(False, f"search failed: {e}")
        if not hits:
            return _result(True, "(no matches)")
        body = "\n\n".join(f"// {h['path']}:{h['start_line']}-{h['end_line']}\n{h['text']}"
                           for h in hits)[:6000]
        return _result(True, body)

    if tool == "run_command":
        argv = action.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            return _result(False, 'argv must be a non-empty list of strings, e.g. ["npm","install"]')
        if not modes.tool_allowed(mode, "run_command"):
            return _result(False, "run_command not allowed in this mode")
        if sandbox.command_needs_confirmation(argv):
            return _result(False, f"refused: '{argv[0]}' is deny-listed in agent mode")
        rc, out = await runner.run_capture(argv, str(base), config.AGENT_COMMAND_TIMEOUT)
        return _result(rc == 0, f"$ {' '.join(argv)} (exit {rc})\n{_clip_error(out, 2000)}")

    if tool == "run_check":
        chk = check_command(base)
        if chk is None:
            return _result(True, "no build system detected — nothing to check")
        rc, out = await runner.run_capture(chk, str(base), config.AGENT_COMMAND_TIMEOUT)
        return _result(rc == 0, f"$ {' '.join(chk)} (exit {rc})\n{_clip_error(out)}")

    return _result(False, f"unknown tool: {tool}")


# --- Context management ------------------------------------------------------
def _trim(messages: list[dict], keep_recent: int = 8) -> list[dict]:
    """Keep system + the first user turn (the task) + the most recent exchanges,
    dropping the middle so a long loop doesn't blow the local model's context."""
    if len(messages) <= keep_recent + 2:
        return messages
    head = messages[:2]  # system + task
    tail = messages[-keep_recent:]
    note = {"role": "user", "content": "[earlier tool observations omitted to save context]"}
    return head + [note] + tail


# --- The worker loop ---------------------------------------------------------
async def run_worker(
    *, emit: Emit, run_id: int, step_id: int, project_id: int, base: Path,
    task_title: str, task_detail: str, goal: str, model: str,
    mode_slug: str, project_rules: str, max_steps: int, cancel,
) -> tuple[bool, str]:
    """Drive one task to completion via the ReAct loop. Returns (success, log_json)."""
    from .pipeline import _file_tree, check_command

    mode = modes.get_mode(mode_slug)
    sys = WORKER_SYSTEM
    if mode and mode.get("system_prompt"):
        sys = mode["system_prompt"] + "\n\n" + sys
    if project_rules:
        sys = project_rules + "\n\n" + sys

    tree = _file_tree(base, limit=120)
    user = (
        f"Overall goal: {goal}\n\n"
        f"YOUR TASK: {task_title}\n{task_detail}\n\n"
        f"Project file tree:\n{tree}\n\n"
        "Begin. Inspect what you need, make the changes, verify the build, then finish."
    )
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
    log: dict = {"messages": [], "tools": []}
    has_check = check_command(base) is not None
    success = False
    summary = ""

    for _ in range(max_steps):
        if cancel.is_set():
            break
        content, _reasoning = await ollama.complete(
            model=model, messages=_trim(messages),
            temperature=config.CODING_TEMPERATURE, top_p=config.CODING_TOP_P,
        )
        log["messages"].append({"role": "worker", "content": content})
        emit("model_message", {"run_id": run_id, "step_id": step_id,
                               "role": "worker", "content": content})
        messages.append({"role": "assistant", "content": content})

        # 1) A write turn: apply FILE:/EDIT: blocks, then auto-run the build.
        wrote, feedback = await _apply_writes(emit, run_id, step_id, base, content, mode, log)
        if wrote or feedback:
            obs = feedback or "Files written."
            if wrote and has_check:
                chk_obs = await _exec_control(
                    emit, run_id, step_id, project_id, base, mode, {"tool": "run_check"}, log)
                obs += "\n\nBuild result:\n" + chk_obs
            messages.append({"role": "user", "content": f"OBSERVATION:\n{obs}"})
            continue

        # 2) A control-action turn.
        action = parse_action(content)
        if action:
            if action["tool"] == "finish":
                summary = str(action.get("summary", "")).strip()
                if has_check:
                    chk_obs = await _exec_control(
                        emit, run_id, step_id, project_id, base, mode,
                        {"tool": "run_check"}, log)
                    if "exit 0" not in chk_obs:
                        messages.append({"role": "user", "content":
                            "OBSERVATION: you called finish but the build is not green:\n"
                            f"{chk_obs}\nFix the errors, then finish again."})
                        continue
                success = True
                break
            obs = await _exec_control(emit, run_id, step_id, project_id, base, mode, action, log)
            messages.append({"role": "user", "content": f"OBSERVATION:\n{obs}"})
            continue

        # 3) Nothing usable — nudge and retry.
        messages.append({"role": "user", "content":
            "OBSERVATION: no valid action found. Respond with exactly ONE fenced JSON "
            "action, or FILE:/EDIT: blocks to change code."})

    log["success"] = success
    log["summary"] = summary
    return success, json.dumps(log)


# --- Orchestrator ------------------------------------------------------------
async def decompose(
    goal: str, base: Path, model: str, project_rules: str, cancel,
) -> list[dict]:
    """Break a large goal into an ordered backlog of self-contained tasks. Each
    task must be independently buildable so the worker can verify it in isolation."""
    from .pipeline import _file_tree, extract_json

    sys = (
        "You are the ORCHESTRATOR of a coding agent. Break the user's goal into an "
        "ORDERED backlog of self-contained tasks that build on each other. Scaffold/"
        "setup first, then one coherent slice of functionality per task, each small "
        "enough that a single agent can finish and BUILD it before the next starts. "
        "Respond with ONLY a JSON object, no prose:\n"
        '{"tasks":[{"title":"short imperative title","detail":"what to do, which '
        'files/areas, and the acceptance check"}]}\n'
        "Use as many tasks as the goal needs (a large app may need 8-15). Order matters."
    )
    if project_rules:
        sys = project_rules + "\n\n" + sys
    tree = _file_tree(base, limit=120)
    user = f"Goal: {goal}\n\nCurrent project files:\n{tree}"
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]

    last_err = ""
    for _ in range(config.AGENT_PLAN_RETRIES + 1):
        if cancel.is_set():
            return []
        content, _r = await ollama.complete(
            model=model, messages=messages, temperature=0.4,
            think="qwen3" in model.lower(),
        )
        try:
            data = extract_json(content)
            tasks = data["tasks"] if isinstance(data, dict) else data
            out = [
                {"title": str(t.get("title", f"Task {i+1}")), "detail": str(t.get("detail", ""))}
                for i, t in enumerate(tasks) if isinstance(t, dict)
            ]
            if out:
                return out
            raise ValueError("empty tasks")
        except Exception as e:
            last_err = str(e)
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content":
                f"That was not valid ({last_err}). Respond with ONLY the JSON object."})
    raise ValueError(f"orchestrator failed to produce a task backlog: {last_err}")
