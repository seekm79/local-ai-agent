# Build Spec: "Workbench" — Local AI Development Studio

You are building a complete local application called **Workbench** from scratch, working phase by phase until every acceptance criterion passes. Read this entire spec before writing any code. Work through the phases in order. At the end of each phase, run the app, verify the acceptance criteria yourself, fix anything broken, then commit with a message like `phase-1: chat core complete` before moving on. Do not skip ahead.

---

## 1. Context and goal

Target machine: **MacBook Pro M5 Max, 64 GB unified memory, macOS**. Everything runs locally, bound to `127.0.0.1` only. No cloud dependencies required for core features.

Workbench replaces the basic Ollama chat experience with a full studio:

- Chat mode and Coding mode over local Ollama models (primary model: `qwen3.6:35b`, helper model: a small ~4–8B model the user selects)
- Projects: each project = a folder on disk + chat history + assets
- VS Code–style code viewing/editing (Monaco) with file tree and embedded terminal
- Run projects: .NET/C#, Flutter, Godot, React/Node — stream output live
- Multi-stage agent pipeline (Planner → Coder → Reviewer loop) with live progress UI
- Rich output rendering: sandboxed HTML/React preview, image gallery, video player
- ComfyUI integration for image/video generation via its local API
- Persistent storage: SQLite for metadata, plain folders for files/assets

## 2. Locked tech stack (do not substitute)

| Layer | Choice |
|---|---|
| Frontend | React 18 + TypeScript + Vite, Tailwind CSS |
| Editor | `@monaco-editor/react` |
| Terminal | `xterm.js` (`@xterm/xterm`) |
| Backend | Python 3.11+, FastAPI, uvicorn |
| LLM access | Ollama OpenAI-compatible API at `http://127.0.0.1:11434/v1` (use the `openai` Python client with a dummy API key) |
| DB | SQLite via `sqlite3` or `aiosqlite` (no ORM required; keep schema in one migrations file) |
| Realtime | WebSockets (FastAPI native) for chat streaming, terminal output, and agent progress |
| Image gen | ComfyUI HTTP + WebSocket API at `http://127.0.0.1:8188` |
| Process mgmt | `asyncio.create_subprocess_exec` (never `shell=True` with user/LLM strings) |

## 3. Repository layout

```
workbench/
├── README.md                  # setup + run instructions (keep updated every phase)
├── Makefile                   # make dev = run backend + frontend concurrently
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS for localhost:5173, routers
│   │   ├── config.py          # paths, model names, ports — all in one place
│   │   ├── db.py              # SQLite init + helpers
│   │   ├── schema.sql
│   │   ├── routers/
│   │   │   ├── chat.py        # WS /ws/chat, REST history endpoints
│   │   │   ├── projects.py    # project CRUD
│   │   │   ├── files.py       # scoped file CRUD
│   │   │   ├── run.py         # command runner + project runners, WS /ws/terminal
│   │   │   ├── agents.py      # pipeline start/status/cancel, WS /ws/agents
│   │   │   └── comfy.py       # ComfyUI proxy endpoints
│   │   ├── services/
│   │   │   ├── ollama.py      # streaming chat, model list, thinking-mode support
│   │   │   ├── sandbox.py     # path validation + command allow/deny logic
│   │   │   ├── runner.py      # subprocess lifecycle, output streaming, kill
│   │   │   ├── pipeline.py    # planner/coder/reviewer orchestration
│   │   │   └── comfy.py       # workflow templating, submit, poll, fetch outputs
│   │   └── tests/             # pytest: sandbox rules, pipeline state machine
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.tsx            # layout shell, mode switcher (Chat | Code | Agents | Build | Assets)
│       ├── api/               # typed fetch + WS clients
│       ├── components/
│       │   ├── chat/          # message list, markdown+code rendering, model picker
│       │   ├── editor/        # file tree, Monaco tabs, save handling
│       │   ├── terminal/      # xterm bound to /ws/terminal
│       │   ├── agents/        # pipeline progress board
│       │   ├── preview/       # sandboxed iframe, image lightbox, video player
│       │   └── assets/        # generated-media gallery
│       └── stores/            # zustand stores: session, project, agents
└── workspace/                 # DEFAULT PROJECTS ROOT (gitignored) — all user projects live here
```

## 4. Global rules (apply to every phase)

**Security — non-negotiable:**
1. Backend binds to `127.0.0.1` only.
2. Every file path from the client or from an LLM must pass `sandbox.resolve_safe(path)`: resolve to absolute, verify it is inside the configured projects root (`workspace/` by default, overridable in config), reject symlinks escaping it. Unit-test this with traversal attacks (`../`, absolute paths, symlinks).
3. Commands run with an explicit argv list. Maintain a deny-list requiring UI confirmation before execution: `rm`, `sudo`, `chmod`, `chown`, `git push --force`, `curl|sh` patterns, anything writing outside the projects root. The confirmation flow: backend returns `{"status":"needs_confirmation", "command":...}`, frontend shows a modal, user approves, backend executes with a one-time token.
4. Never interpolate LLM output into a shell string. Never `eval`.

**Quality:**
5. TypeScript strict mode; Python type hints throughout.
6. Every WS message is a typed JSON envelope: `{"type": "...", "payload": {...}}`. Document all message types in `README.md`.
7. Errors surface in the UI as toasts with the real message — never silent failures.
8. Keep `config.py` the single source of truth for model names, ports, and paths so the user can change them in one place.

**Model usage:**
9. All LLM calls go through `services/ollama.py`. Support per-call model selection, streaming, temperature, and enabling/disabling thinking mode (Qwen3.6 emits reasoning; parse and stream `reasoning`/`thinking` deltas separately from content so the UI can render them collapsed).
10. Default sampling for coding: temperature 0.6, top_p 0.95. Chat: temperature 0.7.
11. Assume `OLLAMA_MAX_LOADED_MODELS=2` so the big model and helper model stay resident; note this in README setup.

---

## Phase 0 — Scaffold

Create the repo layout above, a working `make dev` (backend on :8010, frontend on :5173), health-check endpoint `/api/health`, empty SQLite created from `schema.sql` on first run, and a README with setup steps (Python venv, `npm install`, Ollama prerequisites, model pull commands).

**Accept:** `make dev` starts both servers; visiting the frontend shows the app shell with the four mode tabs; `/api/health` returns model list fetched live from Ollama (`GET /v1/models`).

## Phase 1 — Chat core

- SQLite tables: `projects`, `chats`, `messages` (role, content, reasoning, model, tokens, created_at), `assets`, `agent_runs`, `agent_steps`.
- WS `/ws/chat`: client sends `{type:"user_message", chat_id, content, model, think:bool}`; server streams `{type:"delta", content}` and `{type:"reasoning_delta", content}` then `{type:"done", usage}`. Persist both sides.
- Chat UI: message list with markdown rendering, syntax-highlighted code blocks with copy button, collapsible "thinking" section, model picker populated from Ollama, stop-generation button (cancel the upstream request), chat list sidebar with rename/delete, new-chat button.
- Regenerate last answer and edit-and-resend for the last user message.

**Accept:** Full conversation with `qwen3.6:35b` streams smoothly; thinking content renders collapsed; refresh restores history from SQLite; switching models mid-chat works.

## Phase 2 — Projects, files, editor

- Project CRUD: creating a project creates `workspace/<slug>/` with `assets/` inside; deleting archives the DB row (never deletes files from disk without a confirm modal).
- Files API (all sandbox-validated): list tree, read, write, create, rename, delete, upload (multipart, for images/files the user drags in — store under the project).
- Coding mode UI: left file tree (lazy-loaded folders), center Monaco with tabs, dirty-state indicators, Cmd+S save, language auto-detect for `.cs .dart .gd .tsx .ts .js .html .css .json .md .yaml`; right panel is context-aware chat that automatically includes the open file (path + content, truncated to a configurable char budget) in the system context.
- "Apply to editor" button on assistant code blocks: writes the block to the currently open file after showing a diff preview (use Monaco's diff editor).

**Accept:** Create project → create `main.cs` → edit and save → reopen app → file persists; asking chat to modify the open file and clicking apply shows a diff and updates the file.

## Phase 3 — Terminal and project runners

- WS `/ws/terminal`: spawn a login shell (`zsh -l`) with cwd = active project; frontend xterm sends keystrokes, backend streams output. Support resize messages.
- Command runner API `/api/run/command`: structured execution with the confirmation flow from Global rule 3; streams output over the terminal WS with a distinct message type.
- One-click runners (buttons in Coding mode, enabled by detecting project type from files present):
  - C#: `dotnet run` (detect `.csproj`)
  - Flutter: `flutter run -d macos` (detect `pubspec.yaml`)
  - React/Node: `npm run dev` (detect `package.json`; parse the dev-server URL from output and offer "Open preview")
  - Godot: `godot --headless --export-debug` if configured, else open the project via `godot project.godot` (detect `project.godot`)
- Process manager: list running processes per project, stop button (SIGTERM then SIGKILL after 5s), exit codes shown in UI.

**Accept:** Create a hello-world console C# project via chat + editor, click Run, see output in the terminal panel, stop it; start a Vite React app and open its preview; dangerous command (`rm -rf test`) triggers the confirmation modal.

## Phase 4 — Multi-stage agent pipeline

Implement `services/pipeline.py` as an explicit async state machine (no heavy framework needed):

1. **Planner** (big model, thinking ON): input = user goal + project file tree + key file contents; output = strict JSON plan `{steps:[{id,title,kind:"code|command|review",detail,target_files}]}`. Retry up to 2 times if JSON parsing fails, feeding the parse error back.
2. **Coder** (big model or the `-coding` tag, configurable): executes one step at a time. It can emit tool calls in a constrained JSON format: `write_file {path, content}`, `read_file {path}`, `run_command {argv}` — the backend executes them through the existing sandbox/runner services. Non-allowlisted commands pause the run and surface the confirmation modal.
3. **Reviewer** (big model): after each code step, run the project's check command (`dotnet build`, `flutter analyze`, `npm run build`, or a configured command), feed errors back to the Coder. Max 3 fix iterations per step, then mark the step failed and continue or halt per user setting.
4. **Helper** (small model, runs concurrently since it fits in remaining memory): generates the run summary, commit message suggestion, and per-step one-line status text without blocking the big model.

- Persist every step, every tool call, and every model message to `agent_runs`/`agent_steps` for auditability.
- WS `/ws/agents` streams: run started, step started, tool call, tool result, step passed/failed, run done.
- Agents UI: goal input + project selector + "max iterations" setting; a vertical board showing steps with live status (pending/running/passed/failed), expandable to see the model's output and tool calls; cancel button; final summary card.

**Accept:** Goal "create a C# console app that prints the first 20 Fibonacci numbers and includes a unit test" runs end-to-end: plan appears, files get written, build runs, a failure (if any) triggers a visible fix iteration, run completes with a summary, and all artifacts exist on disk.

## Phase 5 — Rich output rendering

- Preview panel (available in all modes):
  - **HTML**: render any project `.html` file or assistant-generated HTML in a sandboxed iframe (`sandbox="allow-scripts"`, srcdoc; no same-origin).
  - **React app**: iframe pointing at the detected dev-server URL from Phase 3.
  - **Images**: gallery of the project `assets/` folder + any images in the project, lightbox on click, drag-and-drop upload.
  - **Video**: `<video controls>` for `.mp4/.webm/.mov` in the project, served by a backend static route that is sandbox-scoped and supports range requests (required for video seeking).
- Assistant messages containing a full HTML document get an automatic "Preview" button.

**Accept:** Ask chat for "a single-file HTML snake game", click Preview, play it in the iframe; drop a PNG into the gallery and see it persisted under `assets/`; a sample mp4 plays with working seek.

## Phase 6 — ComfyUI integration

- Config: ComfyUI base URL (default `http://127.0.0.1:8188`) and a `workflows/` folder in the repo containing workflow JSON files exported in **API format**. Ship one placeholder text-to-image workflow JSON with clearly marked template slots.
- `services/comfy.py`: load a workflow template, substitute parameters (positive/negative prompt, seed, width, height, steps), POST to `/prompt`, subscribe to ComfyUI's WebSocket (`/ws?clientId=...`) for progress, on completion fetch images via `/view?filename=...&subfolder=...&type=output`, save into the active project's `assets/`, insert an `assets` DB row (prompt, workflow name, params, file path).
- UI: "Generate" tab inside Assets mode — workflow picker, parameter form generated from the template's declared slots, live progress bar, results appear in the gallery. Graceful offline state if ComfyUI isn't running ("ComfyUI not detected at :8188 — start it and retry").
- Agent hook: expose `generate_image {workflow, params}` as a pipeline tool so agent runs can produce game/app assets.

**Accept:** With ComfyUI running and a valid workflow JSON in `workflows/`, generating an image shows progress and lands the file in the gallery + DB; with ComfyUI stopped, the UI shows the offline state without crashing.

## Phase 7 — Polish and hardening

- Settings screen: projects root path, model assignments (planner/coder/reviewer/helper), sampling params, context char budget, deny-list editor, ComfyUI URL. Persist to a `settings` table; hot-reload without restart where feasible.
- Keyboard shortcuts: Cmd+K new chat, Cmd+P file quick-open, Cmd+` toggle terminal.
- Empty states, loading skeletons, and error toasts audited across every screen.
- `pytest` suite green: sandbox traversal cases, deny-list matching, pipeline JSON-plan parsing, runner kill behavior.
- Final README: prerequisites (Ollama models to pull, `OLLAMA_MAX_LOADED_MODELS=2`, optional ComfyUI), `make dev`, feature tour, WS message-type reference, troubleshooting section.

**Accept:** Fresh clone on this Mac reaches a working app following only the README; all tests pass; every prior phase's acceptance checks still pass (re-verify them).

## Phase 8 — Agent intelligence upgrades (Roo Code–inspired)

These eight features are what make mature coding agents feel "smart." Implement them in this order — each one measurably improves the Phase 4 pipeline.

**8.1 Diff-based file editing (highest impact).** Replace whole-file `write_file` as the default with an `apply_diff` tool: the model emits one or more SEARCH/REPLACE blocks (exact original lines → replacement lines). The backend applies them with exact match first, then a whitespace-tolerant fuzzy match fallback; if a block fails to match, return a precise error (the closest candidate region with line numbers) so the model can retry. Why: local models rewriting whole files drift, truncate, and burn tokens; small anchored diffs are far more reliable and faster. Keep `write_file` only for new files. Show every applied diff in the UI using Monaco's diff view.

**8.2 Checkpoints and rollback.** Before each agent step that mutates files, snapshot the project using a shadow git repository (a separate `.workbench/checkpoints.git` with the project as its work tree — never touch the user's own `.git`). UI: a timeline of checkpoints per agent run with one-click "restore project to here" and a diff viewer between any two checkpoints. Why: this makes autonomous runs safe to trust — any mistake is one click from undone.

**8.3 Codebase indexing + semantic search.** Build a local embedding index of the project: chunk source files by function/class where possible (fall back to fixed-size chunks), embed with a local Ollama embedding model (e.g. `nomic-embed-text` or `mxbai-embed-large` — make it configurable), store vectors in SQLite (`sqlite-vec` extension or a simple cosine-similarity table; no external vector DB). Watch the filesystem and re-index changed files incrementally. Expose a `search_codebase {query, top_k}` tool to the pipeline and a search box in Coding mode. Why: the Planner and Coder stop needing the whole tree in context — they retrieve only relevant code, which matters enormously at 35B-model context budgets.

**8.4 Custom modes.** A `modes` table + editor UI where the user defines named agent personas: system instructions, assigned model, sampling params, allowed tools (e.g. a "Reviewer" mode that can read files and run commands but never write), and file-access restrictions by glob (e.g. docs mode can only edit `*.md`). Ship four defaults mirroring the Phase 4 roles (Architect, Coder, Reviewer, Ask) and let the user create more (e.g. "Godot expert" with GDScript-specific instructions). The Phase 4 pipeline reads its role definitions from this table instead of hardcoded prompts.

**8.5 Subtask isolation (orchestrator pattern).** Upgrade the Phase 4 Planner into an orchestrator that can emit a `spawn_subtask {mode, instructions, context_files}` tool call. Each subtask runs in a fresh, isolated model context containing only its instructions and the files it needs, and returns a structured summary to the parent — the parent never sees the subtask's full transcript. Support running independent subtasks concurrently when they touch disjoint files (the small helper model can take some in parallel with the big model). Why: context isolation prevents long runs from degrading — this is the core idea behind Roo Code's orchestrator/Boomerang design, and it matters even more with local models' tighter effective context.

**8.6 Automatic context condensing.** Track token usage per conversation and per agent run. When a thread approaches a configurable threshold (default 70% of `num_ctx`), have the helper model summarize the oldest exchanges into a compact "memory" block (decisions made, files touched, constraints discovered) and replace them. Show a subtle "context condensed" marker in the UI with the summary expandable. Never condense the system instructions or the most recent N messages.

**8.7 Rules files.** On every chat/agent request, automatically load project-level instruction files if present: `.workbench/rules.md` in the project root (and optionally `~/.workbench/rules.md` globally), injected into the system context. Document the convention in README. This lets the user encode "always use Flutter 3 null-safety patterns", "Godot 4.x APIs only, never Godot 3", "C# with file-scoped namespaces" once per project instead of repeating it — and it's the cheapest way to fix a local model's habit of using outdated APIs.

**8.8 Browser tool for web testing.** Add a `browser {action}` pipeline tool backed by Playwright (Chromium, headless): navigate to the dev-server URL from Phase 3, screenshot, click by selector or coordinates, type, read console errors. Screenshots return as images saved to the run's artifacts and shown in the agent board; console errors feed the Reviewer loop. Why: the Reviewer can now verify that the React/Flutter-web app actually renders and works, not just that it compiles. Since Qwen3.6 accepts image input, pass screenshots back to the model for visual verification (make vision use a per-mode toggle — it is token-expensive).

**Accept (Phase 8):** An agent run on a small React project uses `search_codebase` to locate the relevant component, edits it via `apply_diff` (visible as a diff in the UI), a deliberately injected bad edit is undone via checkpoint restore, a subtask runs in isolation and returns only a summary, a long run shows a context-condense event, project rules from `.workbench/rules.md` demonstrably alter output style, and the browser tool screenshots the running app with the screenshot visible in the agent board.

## Phase 9 — The Build tab (Lovable-style app builder)

Build one cohesive tab, **Build**, that reproduces the Lovable web experience end to end: the user describes an app (optionally attaching reference images/files), the agent scaffolds from one fixed template, reads the project's `AGENTS.md` first, designs on top, and streams a live preview the user iterates on by chatting. Uploads and `AGENTS.md` are not separate features here — they are parts of this single flow. Implement all sub-parts together so the tab is complete and Lovable-like on first delivery.

### 9A — The Lovable-style layout and flow

**9.1 Entry screen (empty state).** When no Build project is open, the tab centers on a single large prompt composer, exactly like Lovable's landing: a big multiline input ("Ask Workbench to build something…"), an attach button inside the composer, a submit button, and a row of example prompt chips ("Habit tracker", "SaaS dashboard", "Landing page", "Kanban board") that prefill the input. Submitting creates the project and transitions to the workspace view.

**9.2 Workspace view (two-pane).** After submit, switch to Lovable's core layout: a **left conversation panel** (the running chat with the agent — user prompts, streamed agent reasoning/steps collapsed, and "what changed" summaries) and a **right preview panel** that dominates the screen. Above the preview: a small toolbar with device-width toggles (desktop/tablet/mobile), a light/dark toggle, a refresh button, an "open in new tab" button, and tabs to switch the right pane between **Preview**, **Code** (Monaco file tree + editor, read-mostly but editable), and **Assets**. The left panel's composer stays fixed at the bottom for follow-up requests. This is the "chat on the left, live app on the right" shape users expect from Lovable.

**9.3 Streaming build feedback.** As the agent works, the left panel shows live status the way Lovable does: a compact list of actions ("Designing palette", "Creating dashboard route", "Running build", "Fixing type error") with spinners → checkmarks, each expandable to see detail/diffs. The preview auto-refreshes when the dev server hot-reloads. Never leave the user staring at a blank pane — show skeleton/progress until the first render.

### 9B — Scaffold from the fixed template (never generate from scratch)

**9.4 The base template.** `templates/webapp-base/` in the repo is the immutable starting point for every Build project. Stack is locked: TanStack Start (React 19 + TanStack Router, file-based routes in `src/routes/`), Vite, Tailwind v4, Bun, TypeScript, full shadcn/ui (46 components in `src/components/ui/`, "new-york"). It ships with a root `AGENTS.md` (see 9F). Ship it so `bun install && bun run dev` works out of the box; do not change or upgrade the stack during generation.

**9.5 Scaffold, don't generate.** Starting a Build copies `templates/webapp-base/` into `workspace/<slug>/` and runs `bun install`. Every design action edits this copy. The agent is forbidden — by system-prompt rule AND enforced in code — from replacing the router, rebuilding shadcn primitives, swapping the styling system, or adding a second component library. Reject agent writes that delete `src/components/ui/*` or the `@theme` block of `src/styles.css`.

### 9C — Design on top (the two allowed levers)

**9.6 Retheme the tokens.** All color/radius design lives in `src/styles.css` as `oklch` CSS variables, defined once for light (`:root`) and dark (`.dark`). Restyle by rewriting these variable *values* only — never rename, never hardcode hex/oklch in components. Editable set: `--radius`; and for light+dark: `--background --foreground --card --card-foreground --popover --popover-foreground --primary --primary-foreground --secondary --secondary-foreground --muted --muted-foreground --accent --accent-foreground --destructive --destructive-foreground --border --input --ring --chart-1..5` and the `--sidebar-*` family. All 46 components reference these, so a reskin is a single-file edit. Enforce oklch on save.

**9.7 Compose components into routes.** Build pages by adding files under `src/routes/` importing from `@/components/ui/*` (accordion, alert, alert-dialog, aspect-ratio, avatar, badge, breadcrumb, button, calendar, card, carousel, chart, checkbox, collapsible, command, context-menu, dialog, drawer, dropdown-menu, form, hover-card, input, input-otp, label, menubar, navigation-menu, pagination, popover, progress, radio-group, resizable, scroll-area, select, separator, sheet, sidebar, skeleton, slider, sonner, switch, table, tabs, textarea, toggle, toggle-group, tooltip) plus `lucide-react` and `recharts`. App-specific components go in `src/components/` (never `ui/`). Style with token-mapped Tailwind classes (`bg-primary`, `text-muted-foreground`, `rounded-lg`), never inline colors.

**9.8 Theme panel + regenerate.** The Assets/theme area exposes the current palette as editable swatches with a light/dark toggle; editing a swatch rewrites `styles.css` and hot-reloads. A **"Regenerate design"** action re-runs only the Designer step (new palette, same routes/logic) — the "comes out default, then redesign on top" workflow. Follow-up chat requests ("make the sidebar collapsible", "add a settings page") route through the same build pipeline and update the preview.

### 9D — Build pipeline

**9.9 Mode chain.** Reuse the Phase 4/8 machinery with a Build chain that ALWAYS begins by reading `AGENTS.md` (9F): (a) **Designer** — from the request + any design-reference image + `AGENTS.md`, produce a short design brief and the exact `oklch` palette (all variables, light+dark) and write `src/styles.css`; (b) **Builder** — create routes/components via `apply_diff` (8.1), running `bun run build` after each route as the Reviewer check; (c) **Fixer** — feed build/type errors back, max 3 iterations per route. Persist the design brief to the project so later edits stay consistent.

### 9E — Uploads (reference images and files)

**9.10 Attach anywhere.** The Build composer (and the Chat/Agents composers) has an attach control: click-to-browse, drag-and-drop, and paste-from-clipboard for images. Uploads are stored per-project (`assets/` for media, `uploads/` for docs/data), sandbox-validated (Phase 2), and recorded in the `assets` table. Support images (png/jpg/webp/svg) and text-ish files (md/txt/csv/json/pdf); extract text from PDFs/CSVs server-side so the model reads content, not just filenames. Images pass to the model as vision input where supported (Qwen3.6 does — reuse the 8.8 vision toggle); enforce a size cap and downscale large images before sending.

**9.11 Upload roles in Build.** When a file is attached in Build mode, the user tags it: **design reference** (agent derives palette/layout to match the vibe and adapts it to the template's token system — never a pixel-copy), **asset** (copied to `public/`, used directly in the app), or **content** (data/text the app should display, e.g. a CSV seeded into a table). A design-reference image must visibly shape the Designer step's palette.

**9.12 ComfyUI assets (opt-in).** When a request implies custom visuals (hero image, logo, sprites, illustrations, textures), the agent may call the Phase 6 `generate_image` tool; outputs land in `public/` and are referenced via `<img>` or CSS backgrounds, styled through the tokens. Skip entirely for plain dashboards/CRUD. If ComfyUI is offline, build with placeholder blocks (`bg-muted` panels/skeletons) and mark which assets are pending — a missing ComfyUI never blocks a build.

### 9F — AGENTS.md (read-first project memory)

**9.13 Read first, always.** Every project scaffolds with a root `AGENTS.md` — the single instruction file the agent MUST load and obey before planning or editing, on every request in every mode. Reading it is the unconditional first step of the Build (and Chat/Agents) pipeline. If missing, generate a default and note it. Precedence: explicit user message > `AGENTS.md` > model defaults. Standardize on `AGENTS.md` as the canonical filename (the base template already ships one); if a legacy `.workbench/rules.md` exists, read it too, but write `AGENTS.md` going forward.

**9.14 Contents.** Generated per project from a template with: **Project overview** (one line from the user's request); **Stack and constraints** (for web apps, the 9B/9C rules verbatim; for C#/Flutter/Godot, the framework-version rules); **Design system** (current palette summary + "all color flows through tokens"); **Conventions** (naming, layout, package manager — Bun for web); **Do-not-touch** (`src/components/ui/**`, generated files); **Commands** (install/run/build/test); **User rules** (free section the user edits for standing instructions). Keep it living: when the agent makes a significant design/architecture decision, it appends a short note so future edits stay consistent — the project's durable cross-session memory.

**9.15 AGENTS.md panel.** Expose `AGENTS.md` prominently (a dedicated panel, not buried in the tree) with a Monaco editor, plus an "Agent reads this first" affordance so the behavior is transparent. Edits take effect on the next request.

**Accept (Phase 9):** The empty state shows a centered Lovable-style composer with example chips. "Build me a personal finance dashboard with a warm, editorial look" scaffolds from `templates/webapp-base/`, the left panel streams build steps, and the right panel shows a live preview with working desktop/mobile and light/dark toggles; the app writes a coherent warm oklch palette (light+dark) and composes card/table/chart/sidebar routes that `bun run build` compiles cleanly. Dragging in a PNG tagged "design reference" yields a palette echoing its colors; another tagged "asset" lands in `public/` and appears in the app. "Regenerate design" gives a visibly different palette on the same routes without breaking the build. Deleting `src/components/ui/button.tsx` via an agent write is rejected. Every project has a root `AGENTS.md`; adding "all buttons must be fully rounded" to its User rules and sending a follow-up produces rounded buttons via `--radius`, proving read-first order; removing `AGENTS.md` triggers regeneration before proceeding. With ComfyUI running, "landing page for a coffee brand with a generated hero image" places a generated image in `public/`; with it stopped, the build completes with a placeholder marked pending.

---

## Definition of done

The build is finished only when: all nine phase acceptance checks pass in a single session, the test suite is green, the README is accurate, and the repo has one commit per phase. If you hit an environment blocker (missing SDK, model not pulled, ComfyUI absent), do not fake the feature — implement it fully, add a clear runtime "prerequisite missing" state in the UI, and note the manual step in README.
