# Workbench — Local AI Development Studio

A fully local studio for chatting with, coding against, and building games/apps
with local Ollama models — plus a multi-stage agent pipeline and ComfyUI image
generation. Everything binds to `127.0.0.1` only; no cloud dependencies.

> **Platform note.** The original spec targets macOS (M5 Max). This build runs on
> **Windows 11 / PowerShell**. The architecture is identical; only platform
> bindings differ (PowerShell instead of `zsh`, `dev.ps1` instead of `make dev`,
> `flutter run -d windows`, etc.). All differences are called out below.

---

## Status

| Phase | Feature | State |
|---|---|---|
| 0 | Scaffold: `dev` script, health check, SQLite, app shell | ✅ done |
| 1 | Chat core: streaming, thinking-mode, markdown, sidebar | ✅ done |
| 2 | Projects, files, Monaco editor, context-aware coding chat | ✅ done |
| 3 | Terminal (ConPTY) + project runners + process manager | ✅ done |
| 4 | Multi-stage agent pipeline (Planner→Coder→Reviewer) | ✅ done |
| 5 | Rich output: HTML/React preview, gallery, video | ✅ done |
| 6 | ComfyUI integration (offline-safe; needs ComfyUI to generate) | ✅ done |
| 7 | Polish & hardening (settings, shortcuts, tests) | ✅ done |
| 8 | Agent intelligence upgrades (all 8 sub-features) | ✅ done |
| 9 | Build tab (Lovable-style app builder) | ✅ done |

**Phase 9 — Build tab.** Entry composer + example chips → scaffolds from
`templates/webapp-base` (TanStack Start / React 19 / Tailwind v4 / shadcn, via
**Bun**) and runs `bun install` → two-pane workspace (left: streamed build steps
+ follow-up composer; right: **live preview** iframe with desktop/tablet/mobile +
refresh + open-in-tab, plus **Code**, **AGENTS.md**, and **Theme** tabs). The
**Designer** reads `AGENTS.md` first, then rewrites the `oklch` token *values* in
`src/styles.css` (`:root`/`.dark`, `@theme` preserved) so the live app reskins;
the **Builder** composes routes via `apply_diff` with `bun run build` as the
check. Theme panel = 32 editable oklch swatches + light/dark + **Regenerate
design**. Protected paths (`src/components/ui/**`, `routeTree.gen.ts`, the
`@theme` block) are rejected in code. **Attachments** (📎 in the composer,
drag-drop too) are tagged **design-reference** (dominant colors extracted
server-side and fed to the Designer — no vision model needed), **asset** (copied
to `public/`), or **content** (text extracted from csv/txt/md/json/pdf for the
Builder). An optional **🎨 generate images (ComfyUI)** toggle lets the Builder
produce hero/logo/sprite art into `public/`; offline → a `bg-muted` placeholder.
Prereqs: **Bun** (`npm i -g bun`); `pillow`/`pypdf` (in requirements) for
attachment processing.

**Phase 8 features:** ✅ 8.1 diff-based editing (`apply_diff`, exact + fuzzy match,
precise retry errors, Monaco diff view) · ✅ 8.2 checkpoints/rollback (shadow git
in `.workbench/checkpoints.git`, timeline + restore) · ✅ 8.3 codebase semantic
search (local `nomic-embed-text` embeddings in SQLite, cosine, incremental
reindex, `search_codebase` tool + Code-mode Search tab) · ✅ 8.4 custom modes
(Architect/Coder/Reviewer/Ask + editor; tool + file-glob enforcement) · ✅ 8.5
subtask isolation (orchestrator; disjoint subtasks run concurrently) · ✅ 8.6
context condensing (helper-model summary of old exchanges) · ✅ 8.7 rules /
`AGENTS.md` read-first · ✅ 8.8 browser tool (Playwright headless Chromium:
navigate/screenshot/click/type/console; screenshots in the agent board).

Prereqs for 8.3/8.8: `ollama pull nomic-embed-text` and `pip install playwright &&
playwright install chromium` (both in requirements; the UI shows a clear
prerequisite state if absent).

---

## Prerequisites

- **Python 3.11+** — on this machine use the `py` launcher (`python` is not on PATH).
- **Node 18+ / npm** (tested with Node 22, npm 10).
- **Ollama** running locally at `http://127.0.0.1:11434`.
  Pull the models referenced in `backend/app/config.py`:
  ```powershell
  ollama pull qwen3.6:35b            # primary/big model
  ollama pull nomic-embed-text       # codebase semantic search (Phase 8.3)
  ollama pull qwen2.5-coder:1.5b-base  # small helper model
  ```
  Set the two-model resident limit so the big + helper models stay loaded:
  ```powershell
  setx OLLAMA_MAX_LOADED_MODELS 2
  ```
  (restart the Ollama service after setting it).
- **Optional:** ComfyUI at `http://127.0.0.1:8188` (Phase 6). .NET / Flutter /
  Godot for the project runners (Phase 3). Playwright + Chromium for the browser
  tool (Phase 8.8): `pip install playwright && playwright install chromium`. Each
  has a "prerequisite missing" state in the UI, so the app runs without them.

> Don't have `qwen3.6:35b` yet? The app still runs. The status bar flags the
> missing model; swap in any installed model in `backend/app/config.py`
> (`MODEL_BIG` / `MODEL_HELPER`).

---

## Setup (first time)

**Backend**
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Frontend**
```powershell
cd frontend
npm install
```

---

## Run

From the repo root:
```powershell
./dev.ps1
```
This starts the backend on **:8010** and the frontend on **:5173**. Open
<http://127.0.0.1:5173>.

Prefer running them separately (two terminals):
```powershell
# terminal 1
cd backend; .\.venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload --reload-dir app
# terminal 2
cd frontend; npm run dev
```

On macOS/Linux (or Windows with GNU make installed) `make dev` does the same.

---

## Verify Phase 0

1. `./dev.ps1` starts both servers without errors.
2. <http://127.0.0.1:5173> shows the app shell with four mode tabs:
   **Chat · Code · Agents · Assets**.
3. The status pill (top-right) turns green and lists your Ollama models.
4. <http://127.0.0.1:8010/api/health> returns JSON with a live `models` array
   fetched from Ollama's `GET /v1/models`.
5. `backend/workbench.db` is created on first startup from `schema.sql`.

---

## Feature tour

Four modes across the top, plus a global preview surface and a ⚙ settings panel:

- **Chat** — streaming conversation over local Ollama models; markdown + syntax-
  highlighted code with copy, collapsible "thinking", model picker (installed
  models only), stop / regenerate / edit-and-resend, chat sidebar. A **Preview**
  button appears on any assistant message containing a full HTML document
  (rendered in a sandboxed iframe).
- **Code** — file tree + Monaco tabs (dirty state, `Ctrl+S` save, language auto-
  detect), a context-aware chat that injects the open file, and **Apply to
  editor** (shows a Monaco diff before writing). A bottom panel (`Ctrl+\``) holds
  an interactive terminal and the runners: one-click `dotnet run` / `npm run dev`
  / `flutter run` / `godot` with a process manager, plus a command box that
  routes dangerous commands through a confirmation modal.
- **Agents** — the Planner → Coder → Reviewer pipeline. Enter a goal + project,
  pick a model, watch the live step board (statuses, tool calls, build fix
  iterations) and the final summary.
- **Assets** — media gallery (images with lightbox, inline video with seeking,
  drag-drop upload) and a **Generate** tab for ComfyUI image generation.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+K` | new chat |
| `Ctrl+P` | file quick-open (active project) |
| `Ctrl+\`` | toggle the terminal/run panel (Code mode) |
| `Ctrl+,` | open Settings |

(On macOS these are the `Cmd` equivalents.)

## Project rules — `AGENTS.md` (read-first)

Put an **`AGENTS.md`** in a project root to give the agent standing instructions
it loads and obeys **before** planning or editing, on every chat and agent
request. Use it to pin framework versions and conventions once instead of
repeating them — e.g. "Godot 4.x APIs only, never Godot 3", "C# file-scoped
namespaces", "always fully-rounded buttons". Precedence: **explicit user message
> `AGENTS.md` > model defaults**. A legacy `.workbench/rules.md` and a global
`~/.workbench/rules.md` are also read if present. (Weak local models may not
follow strong style rules reliably — a capable model like `qwen3.6:35b` does.)

## Checkpoints & rollback

Before each agent code step, the project is snapshotted into a **shadow git repo**
at `<project>/.workbench/checkpoints.git` (your own `.git` is never touched). The
Agents panel shows a checkpoint timeline; **restore** resets tracked files to any
checkpoint — one click to undo a bad autonomous edit. Manual snapshots too.

## Configuration

All models, ports, and paths live in **`backend/app/config.py`** — the single
source of truth for defaults. The **⚙ Settings** panel (or `Ctrl+,`) edits most
of them at runtime — model assignments (planner/coder/reviewer/helper), sampling
params, context char budget, projects root, ComfyUI URL, and the command
deny-list — persisting to the `settings` table and **hot-reloading without a
restart**. Common defaults (also overridable via env vars):

| Setting | Default | Env var |
|---|---|---|
| Primary model | `qwen3.6:35b` | `WORKBENCH_MODEL_BIG` |
| Helper model | `phi3:mini` | `WORKBENCH_MODEL_HELPER` |
| Backend port | `8010` | `WORKBENCH_BACKEND_PORT` |
| Projects root | `./workspace` | `WORKBENCH_PROJECTS_ROOT` |
| Ollama URL | `http://127.0.0.1:11434/v1` | `WORKBENCH_OLLAMA_URL` |
| ComfyUI URL | `http://127.0.0.1:8188` | `WORKBENCH_COMFY_URL` |

---

## Architecture

```
backend/   FastAPI + uvicorn, SQLite, WebSockets. All LLM calls go through
           app/services/ollama.py. Binds 127.0.0.1 only.
frontend/  React 18 + TypeScript + Vite + Tailwind. Dev server proxies /api
           and /ws to the backend.
workspace/ Default projects root (gitignored) — user projects live here.
workflows/ ComfyUI workflow templates in API format (Phase 6).
```

### WebSocket message reference

WS envelopes are typed `{ "type": "...", "payload": { ... } }` (Global rule 6).

**`/ws/chat`** — streaming chat.

Client → server:

| type | payload fields | meaning |
|---|---|---|
| `user_message` | `chat_id, content, model, think` | send a new user turn |
| `regenerate` | `chat_id, model, think` | redo the last assistant answer |
| `edit_resend` | `chat_id, message_id, content, model, think` | edit a user message and re-run from there |
| `stop` | — | cancel the in-flight generation |

Server → client:

| type | payload | meaning |
|---|---|---|
| `start` | `{message_id}` | assistant message created; streaming begins |
| `delta` | `{content}` | visible content chunk |
| `reasoning_delta` | `{content}` | collapsed "thinking" chunk |
| `done` | `{message_id, usage}` | finished; `usage` has token counts |
| `stopped` | `{message_id}` | halted by user; partial content persisted |
| `chat_titled` | `{chat_id, title}` | chat auto-titled from first message |
| `error` | `{message}` | real error text for a toast |

**`/ws/terminal?project_id=`** — interactive PTY shell (PowerShell via ConPTY on
Windows / `zsh -l` elsewhere), cwd = project.

| dir | type | payload | meaning |
|---|---|---|---|
| C→S | `input` | `{data}` | keystrokes |
| C→S | `resize` | `{cols, rows}` | terminal resized |
| S→C | `output` | `{data}` | shell output (raw, incl. ANSI) |
| S→C | `exit` | — | shell exited |

**`/ws/run`** — broadcast of managed-process lifecycle (project runners + the
command runner). Server→client only: `run_started` `{...proc}`, `run_output`
`{proc_id, data}`, `run_url` `{proc_id, url}` (parsed dev-server URL),
`run_exited` `{proc_id, exit_code, status}`.

**`/ws/agents`** — agent-pipeline event stream (broadcast). Server→client:
`run_started` `{run_id, goal, steps}`, `step_started`, `model_message`
`{role, content}` (planner/coder/helper), `tool_call` `{tool, args}`,
`tool_result` `{tool, ok, output}`, `step_update` `{status}`, `run_done`
`{status, summary}`, `error`.

### Agent pipeline REST endpoints

| method | path | purpose |
|---|---|---|
| POST | `/api/agents/start` | `{project_id, goal, model?, max_iterations?, halt_on_fail?}` → `{run_id}` |
| GET | `/api/agents/runs` | list runs |
| GET | `/api/agents/runs/{id}` | run + its steps |
| POST | `/api/agents/cancel` | `{run_id}` |

Pipeline design: **Planner** (JSON plan, ≤2 reparse retries) → per step a **Coder**
(writes full files; parser tolerates JSON, `FILE:` markers, or bare code blocks
since local models rarely emit clean JSON) → **Reviewer** (runs `dotnet build` /
`npm run build` / `flutter analyze`, feeds errors back up to `max_iterations`
times) → **Helper** (small instruct model writes the summary). Command/review
steps run the project's check command; agent mode refuses deny-listed commands.
All steps/tool-calls/messages persist to `agent_runs`/`agent_steps`. The pipeline
can also call `generate_image {workflow, params}` as a tool (ComfyUI, Phase 6).

### ComfyUI endpoints (Phase 6)

**`/ws/comfy`** — generation progress: `started`, `progress` `{value, max}`,
`saved` `{path}`, `done` `{paths}`, `error` `{message}`.

| method | path | purpose |
|---|---|---|
| GET | `/api/comfy/status` | `{online, error, url}` — offline-safe |
| GET | `/api/comfy/workflows` | list `workflows/*.json` templates + slots |
| POST | `/api/comfy/generate` | `{project_id, workflow, params}` → async, streams `/ws/comfy` |

Templates in `workflows/*.json` wrap a ComfyUI **API-format** graph with `{{key}}`
placeholders plus a `slots` declaration (drives the Generate form). Shipped:
`workflows/txt2img.json` (SD1.5 — edit `ckpt_name` to a checkpoint installed in
your ComfyUI). Generated images save to the project's `assets/` + an `assets` DB
row. **ComfyUI is optional**: if it isn't running at `:8188`, Assets → Generate
shows an offline notice and disables generation; nothing else is affected.

### Settings endpoints (Phase 7)

| method | path | purpose |
|---|---|---|
| GET | `/api/settings` | effective settings (config defaults + overrides) |
| PUT | `/api/settings` | update a partial set; validates, persists to the `settings` table, applies to `config` live |

### Run / process REST endpoints

| method | path | purpose |
|---|---|---|
| GET | `/api/run/detect?project_id=` | detected runnable types (dotnet/node/flutter/godot) + availability |
| POST | `/api/run/project` | start a runner (`{project_id, kind}`) |
| POST | `/api/run/command` | run a command (`{project_id, argv, cwd}`); dangerous → `needs_confirmation` + token |
| POST | `/api/run/confirm` | execute a confirmed command (`{token}`, one-time) |
| POST | `/api/run/stop` | stop a process (`{proc_id}`) — CTRL_BREAK then `taskkill /T /F` after grace |
| GET | `/api/run/processes?project_id=` | list processes for a project |

Windows notes: `npm`/`flutter` are `.cmd` shims — the runner resolves them on
PATH and wraps in `cmd /c` (CreateProcess can't exec batch files). Process stop
kills the whole tree so `npm → node → esbuild` all die.

### Chat REST endpoints

| method | path | purpose |
|---|---|---|
| GET | `/api/chats` | list chats |
| POST | `/api/chats` | create a chat |
| GET | `/api/chats/{id}/messages` | message history |
| PATCH | `/api/chats/{id}` | rename (`{title}`) |
| DELETE | `/api/chats/{id}` | delete |

Coding-mode chat reuses `/ws/chat` with two extra fields on the generation
messages: `project_id` and `file_path`. When present, the backend injects the
open file (sandbox-read, truncated to `CONTEXT_CHAR_BUDGET`) as system context
and uses the coding sampling params.

### Project & file REST endpoints (all sandbox-validated)

| method | path | purpose |
|---|---|---|
| GET | `/api/projects` | list projects |
| POST | `/api/projects` | create (`{name}`) → makes `workspace/<slug>/assets/` |
| DELETE | `/api/projects/{id}?delete_files=` | archive (default) or hard-delete files |
| GET | `/api/projects/{id}/tree?path=` | list one directory level (lazy) |
| GET | `/api/projects/{id}/read?path=` | read a text file |
| PUT | `/api/projects/{id}/write` | write (`{path, content}`) |
| POST | `/api/projects/{id}/create` | create file/dir (`{path, is_dir}`) |
| POST | `/api/projects/{id}/rename` | rename (`{path, new_path}`) |
| DELETE | `/api/projects/{id}/delete?path=` | delete file/dir |
| POST | `/api/projects/{id}/upload` | multipart upload into a dir |
| GET | `/api/projects/{id}/media` | list image/video files in the project |
| GET | `/api/projects/{id}/raw?path=` | serve raw file bytes (correct content-type, **HTTP Range** for video seeking) |

Every `path` passes `sandbox.resolve_safe()` — traversal (`../`), absolute
paths, and escaping symlinks are rejected (unit-tested in
`app/tests/test_sandbox.py`).

---

## Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest
```

Covers sandbox traversal attacks, command deny-list matching, pipeline JSON-plan
+ coder-output parsing, ComfyUI workflow substitution, runner kill behavior, and
settings hot-reload. (One symlink-escape test is skipped when the OS user can't
create symlinks — expected on Windows without admin.)

## Troubleshooting

- **Status pill red / "backend offline":** the backend isn't running or crashed.
  Check the backend terminal for the traceback.
- **"ollama offline":** Ollama isn't running. Start it and the pill reconnects
  within ~5s (the frontend polls `/api/health`).
- **`py` not found:** install Python 3.11+ and ensure the `py` launcher is on
  PATH, or edit `dev.ps1` to point at your Python.
- **Primary model banner won't clear:** the configured `MODEL_BIG` isn't pulled.
  `ollama pull qwen3.6:35b` (or set a different tag in Settings / `config.py`).
- **Agent run produces empty output:** you selected a *base* model (e.g.
  `qwen2.5-coder:1.5b-base`) — pick an instruct model (`codegemma:7b`,
  `qwen3.6:35b`).
- **Assets → Generate shows "ComfyUI not detected":** ComfyUI isn't running at the
  configured URL. Start it (default `:8188`) and set a checkpoint in the workflow;
  everything else works without it.
- **A runner button says "(missing)":** that SDK (dotnet/node/flutter/godot)
  isn't on PATH. Install it and reopen the project.
