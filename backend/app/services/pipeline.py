"""Multi-stage agent pipeline: Planner -> Coder -> Reviewer, with a small helper
model for the summary. Implemented as an explicit async state machine.

  Planner  (big model, thinking on for capable models): goal + file tree + key
           files -> strict JSON plan of steps.
  Coder    (big/coding model): per step, emits file writes + commands in a
           constrained JSON format, executed through the sandbox + runner.
  Reviewer : runs the project's check command (dotnet build / npm run build /
           flutter analyze); on failure feeds the build output back to the Coder,
           up to AGENT_MAX_FIX_ITERATIONS times.
  Helper   (small model): writes the final run summary + commit-message suggestion.

Every step, tool call, and model message is persisted to agent_runs/agent_steps
and streamed over /ws/agents.

Note: the Coder is single-shot-per-step (current target-file contents are injected
as context, standing in for a read_file tool) — simpler and more reliable than
multi-round tool-calling with small local models. write_file/run_command are still
emitted as tool_call events for the UI/audit trail.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from .. import config, crud
from . import (browser, build, checkpoints, comfy, diff, embeddings, modes,
               ollama, rules, runner, sandbox, uploads)
from .sandbox import SandboxError


# --- JSON extraction ---------------------------------------------------------
def _first_balanced(text: str) -> str | None:
    """Return the first balanced {...} or [...] block, respecting strings."""
    start = None
    opener = closer = ""
    for i, ch in enumerate(text):
        if ch in "{[":
            start, opener = i, ch
            closer = "}" if ch == "{" else "]"
            break
    if start is None:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> dict | list:
    """Best-effort parse of a JSON object/array from a model response."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
    for candidate in (fence.group(1) if fence else None, _first_balanced(text), text):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("no valid JSON found in model output")


# --- Project inspection ------------------------------------------------------
def _file_tree(base: Path, limit: int = 200) -> str:
    lines: list[str] = []
    for p in sorted(base.rglob("*")):
        if any(part in {"obj", "bin", "node_modules", ".git"} for part in p.parts):
            continue
        rel = p.relative_to(base).as_posix()
        lines.append(rel + ("/" if p.is_dir() else ""))
        if len(lines) >= limit:
            break
    return "\n".join(lines) or "(empty project)"


def _read_safe(base: Path, rel: str, budget: int = 4000) -> str:
    try:
        target = sandbox.resolve_safe(base, rel)
    except SandboxError:
        return ""
    if not target.is_file():
        return ""
    try:
        return target.read_text(encoding="utf-8")[:budget]
    except Exception:
        return ""


def check_command(base: Path) -> list[str] | None:
    """The reviewer's build/check command for this project type."""
    if (base / "bunfig.toml").exists() and (base / "package.json").exists():
        return [config.WEB_PACKAGE_MANAGER, "run", "build"]  # Build-tab projects
    if next(base.rglob("*.csproj"), None):
        return ["dotnet", "build"]
    if (base / "package.json").exists():
        try:
            pkg = json.loads((base / "package.json").read_text(encoding="utf-8"))
            if "build" in pkg.get("scripts", {}):
                return ["npm", "run", "build"]
        except Exception:
            pass
        return None
    if (base / "pubspec.yaml").exists():
        return ["flutter", "analyze"]
    return None


def _supports_thinking(model: str) -> bool:
    return "qwen3" in model.lower()


_CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9+#.\-]*\n(.*?)```", re.S)
_FILE_MARKER_RE = re.compile(
    r"FILE:\s*(\S+)\s*```[a-zA-Z0-9+#.\-]*\n(.*?)```", re.S
)


def _clean_path(p: str) -> str:
    """Strip markdown/quote decoration a model may wrap a path in (e.g.
    ``**Program.cs**`` or `` `a.cs` ``) so it's a valid filename."""
    return (p or "").strip().strip("`*\"' ").strip()


def _forbidden_write(rel: str) -> bool:
    """Agent writes into the checkpoint infrastructure are never allowed."""
    norm = rel.replace("\\", "/").lstrip("/")
    return norm == ".workbench" or norm.startswith(".workbench/")


def _disjoint_groups(steps: list[dict]) -> list[list[dict]]:
    """Greedily group subtasks so that within a group no two touch the same
    file. Groups run sequentially; steps within a group run concurrently."""
    groups: list[dict] = []
    for s in steps:
        files = set(s.get("target_files") or [])
        placed = False
        for g in groups:
            if not (files & g["files"]):
                g["steps"].append(s)
                g["files"] |= files
                placed = True
                break
        if not placed:
            groups.append({"steps": [s], "files": set(files)})
    return [g["steps"] for g in groups]


_EDIT_HEADER_RE = re.compile(r"^\s*EDIT:\s*(\S+)\s*$", re.M)


def parse_edits(content: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Parse ``EDIT: <path>`` sections into (path, SEARCH/REPLACE blocks) for
    diff-based editing (8.1). Each section runs until the next EDIT:/FILE:."""
    headers = list(_EDIT_HEADER_RE.finditer(content))
    out: list[tuple[str, list[tuple[str, str]]]] = []
    for i, m in enumerate(headers):
        path = _clean_path(m.group(1))
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        seg = content[start:end]
        file_marker = re.search(r"^\s*FILE:", seg, re.M)
        if file_marker:
            seg = seg[: file_marker.start()]
        blocks = diff.parse_blocks(seg)
        if path and blocks:
            out.append((path, blocks))
    return out


def parse_coder(content: str, targets: list[str]) -> tuple[list[dict], list[list]]:
    """Parse coder output into (files, commands), tolerant of weak local models.

    Tries, in order: strict JSON {files, commands}; ``FILE: path`` + fenced
    block markers; bare fenced code blocks mapped onto the step's target_files.
    """
    # 1) strict JSON
    try:
        data = extract_json(content)
        if isinstance(data, dict) and ("files" in data or "commands" in data):
            files = [
                {"path": _clean_path(f["path"]), "content": f.get("content", "")}
                for f in data.get("files", [])
                if isinstance(f, dict) and f.get("path")
            ]
            cmds = [c for c in data.get("commands", []) if isinstance(c, list) and c]
            if files or cmds:
                return files, cmds
    except Exception:
        pass

    # 2) FILE: markers
    marked = [
        {"path": _clean_path(m.group(1)), "content": m.group(2)}
        for m in _FILE_MARKER_RE.finditer(content)
    ]
    marked = [f for f in marked if f["path"]]
    if marked:
        return marked, []

    # 3) bare code blocks mapped onto known target files
    blocks = _CODE_BLOCK_RE.findall(content)
    if targets and blocks:
        if len(targets) == 1:
            best = max(blocks, key=len)  # the most complete block
            return [{"path": targets[0], "content": best}], []
        return (
            [{"path": t, "content": b} for t, b in zip(targets, blocks)],
            [],
        )
    return [], []


# --- Pipeline ----------------------------------------------------------------
class Pipeline:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._tasks: dict[int, asyncio.Task] = {}
        self._cancels: dict[int, asyncio.Event] = {}

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def _emit(self, type_: str, payload: dict) -> None:
        event = {"type": type_, "payload": payload}
        for q in list(self._subs):
            q.put_nowait(event)

    def start(
        self,
        *,
        run_id: int,
        project_id: int,
        goal: str,
        model: str,
        helper_model: str,
        max_iterations: int,
        halt_on_fail: bool,
    ) -> None:
        cancel = asyncio.Event()
        self._cancels[run_id] = cancel
        task = asyncio.create_task(
            self._run(
                run_id=run_id,
                project_id=project_id,
                goal=goal,
                model=model,
                helper_model=helper_model,
                max_iterations=max_iterations,
                halt_on_fail=halt_on_fail,
                cancel=cancel,
            )
        )
        self._tasks[run_id] = task

    def cancel(self, run_id: int) -> bool:
        ev = self._cancels.get(run_id)
        if ev:
            ev.set()
            return True
        return False

    # --- state machine -------------------------------------------------------
    async def _run(
        self,
        *,
        run_id: int,
        project_id: int,
        goal: str,
        model: str,
        helper_model: str,
        max_iterations: int,
        halt_on_fail: bool,
        cancel: asyncio.Event,
    ) -> None:
        proj = crud.get_project(project_id)
        base = Path(proj["path"]) if proj else None
        try:
            if base is None:
                raise ValueError("project not found")

            crud.update_run(run_id, "running")

            # Read-first project rules (8.7) and an initial checkpoint (8.2).
            project_rules = rules.load_rules(project_id)
            try:
                cp = await checkpoints.snapshot(project_id, "before agent run")
                self._emit("checkpoint", {"run_id": run_id, **cp})
            except Exception:
                pass  # checkpoints are best-effort (e.g. git missing)

            # 1) PLAN
            steps = await self._plan(run_id, goal, base, model, project_rules, cancel)
            step_rows = []
            for i, s in enumerate(steps):
                row = crud.create_step(
                    run_id, i, s.get("kind", "code"), s.get("title", f"Step {i+1}"),
                    s.get("detail", ""),
                )
                row["target_files"] = s.get("target_files", [])
                row["mode"] = s.get("mode")  # for subtask steps (8.5)
                step_rows.append(row)
            self._emit(
                "run_started",
                {"run_id": run_id, "goal": goal, "steps": [
                    {k: r[k] for k in ("id", "idx", "kind", "title", "detail", "status")}
                    | {"target_files": r["target_files"]}
                    for r in step_rows
                ]},
            )

            # 2) EXECUTE STEPS. Consecutive subtask steps run concurrently when
            # they touch disjoint files (8.5 orchestrator pattern).
            any_failed = False
            i = 0
            while i < len(step_rows):
                if cancel.is_set():
                    break
                if step_rows[i]["kind"] == "subtask":
                    batch = []
                    while i < len(step_rows) and step_rows[i]["kind"] == "subtask":
                        batch.append(step_rows[i])
                        i += 1
                    try:
                        cp = await checkpoints.snapshot(project_id, "before subtasks")
                        self._emit("checkpoint", {"run_id": run_id, **cp})
                    except Exception:
                        pass
                    for group in _disjoint_groups(batch):
                        results = await asyncio.gather(*[
                            self._execute_step(run_id, project_id, base, goal, s,
                                               model, project_rules, max_iterations,
                                               cancel)
                            for s in group
                        ])
                        if not all(results):
                            any_failed = True
                    if any_failed and halt_on_fail:
                        break
                else:
                    ok = await self._execute_step(
                        run_id, project_id, base, goal, step_rows[i], model,
                        project_rules, max_iterations, cancel
                    )
                    i += 1
                    if not ok:
                        any_failed = True
                        if halt_on_fail:
                            break

            if cancel.is_set():
                crud.update_run(run_id, "cancelled")
                self._emit("run_done", {"run_id": run_id, "status": "cancelled",
                                        "summary": "Run cancelled by user."})
                return

            # 3) HELPER SUMMARY (small model)
            status = "failed" if any_failed else "done"
            summary = await self._summarize(run_id, goal, helper_model)
            crud.update_run(run_id, status, summary)
            self._emit("run_done", {"run_id": run_id, "status": status, "summary": summary})

        except Exception as exc:
            crud.update_run(run_id, "failed", f"error: {exc}")
            self._emit("error", {"run_id": run_id, "message": f"{type(exc).__name__}: {exc}"})
            self._emit("run_done", {"run_id": run_id, "status": "failed",
                                    "summary": f"Run failed: {exc}"})
        finally:
            self._cancels.pop(run_id, None)
            self._tasks.pop(run_id, None)

    async def _plan(
        self, run_id: int, goal: str, base: Path, model: str, project_rules: str,
        cancel: asyncio.Event,
    ) -> list[dict]:
        tree = _file_tree(base)
        sys = (
            "You are the PLANNER in a coding agent. Break the user's goal into a "
            "short ordered list of concrete steps. Respond with ONLY a JSON object, "
            "no prose, in exactly this shape:\n"
            '{"steps":[{"id":1,"title":"...","kind":"code|command|review|subtask",'
            '"detail":"what to do","target_files":["relative/path"],"mode":"coder"}]}\n'
            "Prefer 2-5 steps. Use kind 'code' for writing/editing files, 'command' "
            "for running a build/test command, 'review' for a final build check, and "
            "'subtask' to delegate an isolated unit of work to a mode (set 'mode'); "
            "consecutive subtasks on disjoint target_files run concurrently."
        )
        architect = modes.get_mode("architect")
        if architect and architect.get("system_prompt"):
            sys = architect["system_prompt"] + "\n\n" + sys
        if project_rules:
            sys = project_rules + "\n\n" + sys
        user = f"Goal: {goal}\n\nProject files:\n{tree}"
        messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]

        last_err = ""
        for attempt in range(config.AGENT_PLAN_RETRIES + 1):
            if cancel.is_set():
                return []
            content, reasoning = await ollama.complete(
                model=model, messages=messages, temperature=0.4,
                think=_supports_thinking(model),
            )
            self._emit("model_message", {"run_id": run_id, "step_id": None,
                                         "role": "planner", "content": content,
                                         "reasoning": reasoning})
            try:
                data = extract_json(content)
                steps = data["steps"] if isinstance(data, dict) else data
                if not isinstance(steps, list) or not steps:
                    raise ValueError("empty steps")
                return steps
            except Exception as e:
                last_err = str(e)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content":
                    f"That was not valid. Error: {last_err}. Respond with ONLY the "
                    "JSON object in the required shape."})
        raise ValueError(f"planner failed to produce valid JSON: {last_err}")

    async def _execute_step(
        self, run_id: int, project_id: int, base: Path, goal: str, step: dict,
        model: str, project_rules: str, max_iterations: int, cancel: asyncio.Event,
    ) -> bool:
        step_id = step["id"]
        crud.update_step(step_id, "running")
        self._emit("step_started", {"run_id": run_id, "step_id": step_id,
                                    "idx": step["idx"], "title": step["title"],
                                    "kind": step["kind"]})
        log: dict = {"messages": [], "tools": []}

        # Review AND command steps just run the project's check command — we
        # don't let a weak model synthesize arbitrary argv from NL, and a code
        # block on a command step must not overwrite a target file (e.g. .csproj).
        if step["kind"] in ("review", "command"):
            ok = await self._review(run_id, step_id, base, log)
            crud.update_step(step_id, "passed" if ok else "failed", json.dumps(log))
            self._emit("step_update", {"run_id": run_id, "step_id": step_id,
                                       "status": "passed" if ok else "failed"})
            return ok

        is_subtask = step["kind"] == "subtask"
        # Checkpoint before a (non-concurrent) code step mutates files (8.2).
        # Subtasks are snapshotted once as a batch in _run to avoid concurrent
        # git index locks.
        if not is_subtask:
            try:
                cp = await checkpoints.snapshot(project_id, f"before: {step['title']}")
                self._emit("checkpoint", {"run_id": run_id, "step_id": step_id, **cp})
            except Exception:
                pass

        # code steps: coder emits diffs/files, then reviewer builds. Subtasks skip
        # the per-step build (concurrent builds would collide on obj/bin).
        build_errors = ""
        passed = False
        chk = None if is_subtask else check_command(base)
        for it in range(max_iterations):
            if cancel.is_set():
                break
            edit_feedback = await self._code(run_id, project_id, step_id, base, goal,
                                             step, build_errors, model, project_rules, log)
            # Diff blocks that didn't match feed straight back for a retry.
            if edit_feedback:
                build_errors = edit_feedback[-4000:]
                if it < max_iterations - 1:
                    self._emit("step_update", {"run_id": run_id, "step_id": step_id,
                                               "status": f"fixing (attempt {it + 2})"})
                continue
            # Reviewer: build check (if the project has one).
            if chk is None:
                passed = True
                break
            rc, out = await self._run_check(run_id, step_id, base, chk, log)
            if rc == 0:
                passed = True
                break
            build_errors = out[-4000:]
            self._emit("step_update", {"run_id": run_id, "step_id": step_id,
                                       "status": f"fixing (attempt {it + 2})"})

        crud.update_step(step_id, "passed" if passed else "failed", json.dumps(log))
        self._emit("step_update", {"run_id": run_id, "step_id": step_id,
                                   "status": "passed" if passed else "failed"})
        return passed

    async def _code(
        self, run_id: int, project_id: int, step_id: int, base: Path, goal: str,
        step: dict, build_errors: str, model: str, project_rules: str, log: dict,
    ) -> str:
        """Run the coder for one step. Returns "" on success, or feedback text to
        feed back into the next fix iteration (diff/parse errors)."""
        targets = step.get("target_files") or []
        current = "\n\n".join(
            f"--- {t} ---\n{_read_safe(base, t) or '(new file — does not exist yet)'}"
            for t in targets
        ) or "(no target files listed)"
        sys = (
            "You are the CODER in a coding agent. Prefer small, anchored edits.\n"
            "EDIT an existing file with one or more SEARCH/REPLACE blocks — the "
            "SEARCH text must copy the CURRENT lines EXACTLY:\n"
            "EDIT: <relative/path>\n"
            "<<<<<<< SEARCH\n<exact current lines>\n=======\n<new lines>\n>>>>>>> REPLACE\n"
            "CREATE a new file with its full contents:\n"
            "FILE: <relative/path>\n```\n<full contents>\n```\n"
            "Use EDIT for files that already exist, FILE only for new files. "
            "No explanations."
        )
        # Subtasks run in an isolated context under their own mode (8.4/8.5).
        mode_slug = step.get("mode") or "coder"
        coder_mode = modes.get_mode(mode_slug)
        if coder_mode and coder_mode.get("system_prompt"):
            sys = coder_mode["system_prompt"] + "\n\n" + sys
        if project_rules:
            sys = project_rules + "\n\n" + sys

        # search_codebase (8.3): retrieve the most relevant existing code so the
        # coder edits the right place without the whole tree in context.
        retrieved = ""
        if modes.tool_allowed(coder_mode, "search_codebase") and \
                embeddings.chunk_count(project_id) > 0:
            query = f"{step['title']} {step.get('detail','')}"
            self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                     "tool": "search_codebase", "args": {"query": query}})
            try:
                hits = await embeddings.search(project_id, query, top_k=4)
            except Exception:
                hits = []
            if hits:
                retrieved = "\n\n".join(
                    f"// {h['path']}:{h['start_line']}-{h['end_line']}\n{h['text']}"
                    for h in hits
                )[:6000]
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "search_codebase", "ok": True,
                                           "output": "top: " + ", ".join(
                                               f"{h['path']}:{h['start_line']}" for h in hits)})

        goal_line = "" if step.get("kind") == "subtask" else f"Goal: {goal}\n\n"
        user = (
            f"{goal_line}Step: {step['title']}\nDetail: {step.get('detail','')}\n\n"
            f"Target files: {', '.join(targets) or '(decide from the step)'}\n\n"
            f"Current target files:\n{current}"
        )
        if retrieved:
            user += f"\n\nRelevant existing code:\n{retrieved}"
        if build_errors:
            user += f"\n\nThe previous attempt failed with:\n{build_errors}\n\nFix it."
        content, _ = await ollama.complete(
            model=model, messages=[{"role": "system", "content": sys},
                                   {"role": "user", "content": user}],
            temperature=config.CODING_TEMPERATURE, top_p=config.CODING_TOP_P,
        )
        log["messages"].append({"role": "coder", "content": content})
        self._emit("model_message", {"run_id": run_id, "step_id": step_id,
                                     "role": "coder", "content": content})

        edits = parse_edits(content)
        edited_paths = {p for p, _ in edits}
        files, commands = parse_coder(content, targets)
        # Don't let a bare-code-block fallback clobber a file we're diff-editing.
        files = [f for f in files if _clean_path(f.get("path", "")) not in edited_paths]

        if not edits and not files and not commands:
            self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                       "tool": "parse", "ok": False,
                                       "output": "no EDIT/FILE blocks or commands found"})
            return ("You produced no usable output. Emit SEARCH/REPLACE EDIT blocks "
                    "for existing files or a FILE block for a new file.")

        feedback: list[str] = []

        # apply_diff tool calls (8.1)
        for path, blocks in edits:
            self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                     "tool": "apply_diff",
                                     "args": {"path": path, "blocks": len(blocks)}})
            if _forbidden_write(path) or build.is_protected(path):
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "apply_diff", "ok": False,
                                           "output": f"refused: {path} is protected/reserved"})
                feedback.append(f"{path} is protected (shadcn ui/, generated files, "
                                "or .workbench/) — do not modify it")
                continue
            if not modes.tool_allowed(coder_mode, "apply_diff"):
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "apply_diff", "ok": False,
                                           "output": "refused: apply_diff not allowed in this mode"})
                feedback.append("editing files is not allowed in the current mode")
                continue
            if not modes.path_allowed(coder_mode, path):
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "apply_diff", "ok": False,
                                           "output": f"refused: {path} outside this mode's file scope"})
                feedback.append(f"{path} is outside the allowed file globs for this mode")
                continue
            try:
                target = sandbox.resolve_safe(base, path)
            except SandboxError as e:
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "apply_diff", "ok": False,
                                           "output": f"blocked: {e}"})
                feedback.append(f"{path}: blocked ({e})")
                continue
            before = target.read_text(encoding="utf-8") if target.is_file() else ""
            after, results = diff.apply_blocks(before, blocks)
            failed = [r for r in results if not r.ok]
            if failed:
                errtext = " | ".join(r.error or "match failed" for r in failed)
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "apply_diff", "ok": False,
                                           "output": errtext})
                feedback.append(f"apply_diff on {path} failed: {errtext}")
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(after, encoding="utf-8")
            except OSError as e:
                feedback.append(f"{path}: write failed ({e})")
                continue
            log["tools"].append({"tool": "apply_diff", "path": path, "ok": True})
            self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                       "tool": "apply_diff", "ok": True,
                                       "output": f"{path}: applied {len(blocks)} block(s)",
                                       "path": path, "before": before, "after": after})

        # write_file tool calls (new files only)
        for f in files:
            path, body = f.get("path"), f.get("content", "")
            if not path:
                continue
            self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                     "tool": "write_file", "args": {"path": path}})
            if _forbidden_write(path) or build.is_protected(path):
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "write_file", "ok": False,
                                           "output": f"refused: {path} is protected/reserved"})
                feedback.append(f"{path} is protected (shadcn ui/, generated files, "
                                "or .workbench/) — do not modify it")
                continue
            if not modes.tool_allowed(coder_mode, "write_file"):
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "write_file", "ok": False,
                                           "output": "refused: write_file not allowed in this mode"})
                feedback.append("creating files is not allowed in the current mode")
                continue
            if not modes.path_allowed(coder_mode, path):
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "write_file", "ok": False,
                                           "output": f"refused: {path} outside this mode's file scope"})
                feedback.append(f"{path} is outside the allowed file globs for this mode")
                continue
            try:
                target = sandbox.resolve_safe(base, path)
                before = target.read_text(encoding="utf-8") if target.is_file() else ""
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
                ok, msg = True, f"wrote {len(body)} bytes"
            except SandboxError as e:
                ok, msg, before = False, f"blocked: {e}", ""
            except OSError as e:
                ok, msg, before = False, f"write failed: {e}", ""
            log["tools"].append({"tool": "write_file", "path": path, "ok": ok})
            evt = {"run_id": run_id, "step_id": step_id, "tool": "write_file",
                   "ok": ok, "output": f"{path}: {msg}"}
            if ok:
                evt.update({"path": path, "before": before, "after": body})
            self._emit("tool_result", evt)

        # run_command tool calls (agent mode refuses dangerous commands)
        for argv in commands:
            if not isinstance(argv, list) or not argv:
                continue
            self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                     "tool": "run_command", "args": {"argv": argv}})
            if sandbox.command_needs_confirmation(argv):
                self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                           "tool": "run_command", "ok": False,
                                           "output": "refused: dangerous command not "
                                           "allowed in agent mode"})
                continue
            rc, out = await runner.run_capture(argv, str(base),
                                               config.AGENT_COMMAND_TIMEOUT)
            log["tools"].append({"tool": "run_command", "argv": argv, "rc": rc})
            self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                       "tool": "run_command", "ok": rc == 0,
                                       "output": f"$ {' '.join(argv)} (exit {rc})\n{out[-2000:]}"})

        # generate_image tool (Phase 6 hook): agent runs can produce assets via
        # ComfyUI. Degrades gracefully to an error tool_result when ComfyUI is off.
        gens = []
        try:
            d = extract_json(content)
            if isinstance(d, dict):
                gens = d.get("generate_image") or []
        except Exception:
            gens = []
        for g in gens:
            if not isinstance(g, dict):
                continue
            self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                     "tool": "generate_image", "args": g})
            events: list[tuple[str, dict]] = []

            async def _cb(t: str, p: dict, _ev=events) -> None:
                _ev.append((t, p))

            await comfy.generate(project_id, g.get("workflow", "txt2img.json"),
                                 g.get("params", {}), _cb)
            err = next((p["message"] for t, p in events if t == "error"), None)
            saved = [p["path"] for t, p in events if t == "saved"]
            log["tools"].append({"tool": "generate_image", "ok": err is None})
            self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                       "tool": "generate_image", "ok": err is None,
                                       "output": err or f"generated {len(saved)} image(s)"})

        # browser tool (8.8): screenshot/verify a running dev server. Console
        # errors feed back to the fix loop (the Reviewer signal).
        browser_req = None
        try:
            d = extract_json(content)
            if isinstance(d, dict):
                browser_req = d.get("browser")
        except Exception:
            browser_req = None
        if browser_req and modes.tool_allowed(coder_mode, "browser"):
            url = browser_req.get("url") if isinstance(browser_req, dict) else None
            actions = browser_req.get("actions", []) if isinstance(browser_req, dict) else []
            self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                     "tool": "browser", "args": {"url": url}})
            result = await browser.run(url, actions, base / "assets" / "browser")
            urls = [f"/api/projects/{project_id}/raw?path=assets/browser/{n}"
                    for n in result.get("screenshots", [])]
            errs = result.get("console_errors", [])
            log["tools"].append({"tool": "browser", "ok": not result.get("error")})
            self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                       "tool": "browser",
                                       "ok": not result.get("error") and not errs,
                                       "output": result.get("error") or
                                       (f"{len(errs)} console error(s)" if errs else "ok"),
                                       "screenshots": urls})
            if errs:
                feedback.append("browser console errors: " + " | ".join(errs[:5]))

        return "\n".join(feedback)

    async def _run_check(
        self, run_id: int, step_id: int, base: Path, chk: list[str], log: dict,
    ) -> tuple[int, str]:
        self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                 "tool": "review", "args": {"argv": chk}})
        rc, out = await runner.run_capture(chk, str(base), config.AGENT_COMMAND_TIMEOUT)
        log["tools"].append({"tool": "review", "argv": chk, "rc": rc})
        self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                   "tool": "review", "ok": rc == 0,
                                   "output": f"$ {' '.join(chk)} (exit {rc})\n{out[-2000:]}"})
        return rc, out

    async def _review(self, run_id: int, step_id: int, base: Path, log: dict) -> bool:
        chk = check_command(base)
        if chk is None:
            self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                       "tool": "review", "ok": True,
                                       "output": "no build system detected — skipped"})
            return True
        rc, _ = await self._run_check(run_id, step_id, base, chk, log)
        return rc == 0

    async def _summarize(self, run_id: int, goal: str, helper_model: str) -> str:
        steps = crud.list_steps(run_id)
        outcome = "\n".join(f"- [{s['status']}] {s['title']}" for s in steps)
        sys = ("You are a concise assistant. In 2-4 sentences summarize the agent "
               "run for the user, then suggest a one-line git commit message.")
        user = f"Goal: {goal}\n\nSteps:\n{outcome}"
        try:
            content, _ = await ollama.complete(
                model=helper_model,
                messages=[{"role": "system", "content": sys},
                          {"role": "user", "content": user}],
                temperature=0.5,
            )
            self._emit("model_message", {"run_id": run_id, "step_id": None,
                                         "role": "helper", "content": content})
            return content.strip() or outcome
        except Exception:
            # Helper is best-effort; fall back to a plain outcome list.
            return f"Goal: {goal}\n{outcome}"


    # --- Build tab (Phase 9) --------------------------------------------------
    async def _design(self, run_id, project_id, base, request, project_rules,
                      model, step, reference_colors=None) -> bool:
        """Designer step: produce an oklch palette matching the request and
        rewrite the token values in src/styles.css (9.6). A design-reference
        image's dominant colors (if attached) seed the palette (9.11)."""
        step_id = step["id"]
        crud.update_step(step_id, "running")
        self._emit("step_started", {"run_id": run_id, "step_id": step_id,
                                    "idx": step["idx"], "title": step["title"],
                                    "kind": "design"})
        log: dict = {"messages": [], "tools": []}
        tokens = ", ".join(build.CORE_TOKENS)
        sys = (
            "You are the DESIGNER. Produce a cohesive color palette that matches "
            "the request's vibe. Respond with ONLY a JSON object:\n"
            '{"brief":"one line describing the look","radius":"0.625rem",'
            '"light":{"background":"oklch(...)", ...},"dark":{"background":"oklch(...)", ...}}\n'
            "EVERY color value MUST be in oklch() form. Set these tokens in both "
            f"light and dark: {tokens}."
        )
        if reference_colors:
            sys += ("\n\nThe user attached a design reference; base the palette on "
                    "these dominant colors (adapt to the token system, don't "
                    f"pixel-copy): {', '.join(reference_colors[:6])}.")
        if project_rules:
            sys = project_rules + "\n\n" + sys
        styles_path = base / "src" / "styles.css"
        before = styles_path.read_text(encoding="utf-8")
        user = (f"Request: {request}\n\nRewrite only the :root (light) and .dark "
                f"token values. Current styles.css:\n{before[:3500]}")
        content, _ = await ollama.complete(
            model=model, messages=[{"role": "system", "content": sys},
                                   {"role": "user", "content": user}],
            temperature=0.85,
        )
        log["messages"].append({"role": "designer", "content": content})
        self._emit("model_message", {"run_id": run_id, "step_id": step_id,
                                     "role": "designer", "content": content})
        try:
            palette = extract_json(content)
            if not isinstance(palette, dict) or "light" not in palette:
                raise ValueError("missing light palette")
            build.apply_palette(base, palette)
        except Exception as exc:
            self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                       "tool": "design", "ok": False,
                                       "output": f"palette failed: {exc}"})
            crud.update_step(step_id, "failed", json.dumps(log))
            self._emit("step_update", {"run_id": run_id, "step_id": step_id,
                                       "status": "failed"})
            return False

        after = styles_path.read_text(encoding="utf-8")
        brief = palette.get("brief", "new palette applied")
        self._emit("tool_call", {"run_id": run_id, "step_id": step_id,
                                 "tool": "apply_diff", "args": {"path": "src/styles.css"}})
        self._emit("tool_result", {"run_id": run_id, "step_id": step_id,
                                   "tool": "apply_diff", "ok": True, "output": brief,
                                   "path": "src/styles.css", "before": before, "after": after})
        log["tools"].append({"tool": "apply_palette", "ok": True})
        build_append_design(base, brief)
        crud.update_step(step_id, "passed", json.dumps(log))
        self._emit("step_update", {"run_id": run_id, "step_id": step_id,
                                   "status": "passed"})
        return True

    def start_build(self, *, run_id, project_id, request, model, helper_model,
                    max_iterations, design_only=False, generate_images=False):
        cancel = asyncio.Event()
        self._cancels[run_id] = cancel
        self._tasks[run_id] = asyncio.create_task(self._run_build(
            run_id=run_id, project_id=project_id, request=request, model=model,
            helper_model=helper_model, max_iterations=max_iterations,
            cancel=cancel, design_only=design_only, generate_images=generate_images))

    async def _run_build(self, *, run_id, project_id, request, model, helper_model,
                         max_iterations, cancel, design_only, generate_images=False):
        proj = crud.get_project(project_id)
        base = Path(proj["path"]) if proj else None
        try:
            if base is None:
                raise ValueError("project not found")
            crud.update_run(run_id, "running")
            project_rules = rules.load_rules(project_id)  # AGENTS.md read-first (9.13)
            try:
                cp = await checkpoints.snapshot(project_id, "before build")
                self._emit("checkpoint", {"run_id": run_id, **cp})
            except Exception:
                pass

            # Attachments (9.10/9.11): design-reference colors seed the Designer;
            # content text feeds the Builder.
            attachments = uploads.list_attachments(project_id)
            ref_colors = [c for a in attachments if a["role"] == "design_reference"
                          for c in a.get("colors", [])]
            content_blocks = [f"# {a['path']}\n{a['text']}" for a in attachments
                              if a["role"] == "content" and a.get("text")]

            design_row = crud.create_step(run_id, 0, "design", "Designer — palette", request)
            design_row["target_files"] = []
            design_row["mode"] = None
            step_rows = [design_row]
            if not design_only:
                build_detail = request
                if content_blocks:
                    build_detail += "\n\nAttached content to display:\n" + \
                        "\n\n".join(content_blocks)[:6000]
                if generate_images:
                    build_detail += (
                        "\n\nYou MAY call generate_image {workflow, params} to "
                        "create hero images/logos/sprites; save into public/ and "
                        "reference via <img> or bg. If it fails (ComfyUI offline), "
                        "use a bg-muted placeholder and note it as pending.")
                build_row = crud.create_step(run_id, 1, "code",
                                             "Builder — compose routes", build_detail)
                build_row["target_files"] = ["src/routes/index.tsx"]
                build_row["mode"] = "coder"
                step_rows.append(build_row)

            self._emit("run_started", {"run_id": run_id, "goal": request, "steps": [
                {k: r[k] for k in ("id", "idx", "kind", "title", "detail", "status")}
                | {"target_files": r["target_files"]} for r in step_rows]})

            any_failed = not await self._design(run_id, project_id, base, request,
                                                 project_rules, model, design_row,
                                                 ref_colors)
            if not design_only and not cancel.is_set():
                ok = await self._execute_step(run_id, project_id, base, request,
                                              step_rows[1], model, project_rules,
                                              max_iterations, cancel)
                if not ok:
                    any_failed = True

            summary = await self._summarize(run_id, request, helper_model)
            status = "cancelled" if cancel.is_set() else ("failed" if any_failed else "done")
            crud.update_run(run_id, status, summary)
            self._emit("run_done", {"run_id": run_id, "status": status, "summary": summary})
        except Exception as exc:
            crud.update_run(run_id, "failed", f"error: {exc}")
            self._emit("error", {"run_id": run_id, "message": f"{type(exc).__name__}: {exc}"})
            self._emit("run_done", {"run_id": run_id, "status": "failed",
                                    "summary": f"Build failed: {exc}"})
        finally:
            self._cancels.pop(run_id, None)
            self._tasks.pop(run_id, None)


def build_append_design(base: Path, brief: str) -> None:
    """Append a design decision note to AGENTS.md (9.14 living memory)."""
    agents = base / "AGENTS.md"
    if not agents.is_file() or not brief:
        return
    try:
        text = agents.read_text(encoding="utf-8")
        marker = "## Design system"
        if marker in text:
            idx = text.index(marker) + len(marker)
            note = f"\n\n- {brief}"
            text = text[:idx] + note + text[idx:]
            agents.write_text(text, encoding="utf-8")
    except Exception:
        pass


pipeline = Pipeline()
