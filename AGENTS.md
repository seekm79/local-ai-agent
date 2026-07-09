# AGENTS.md

Guidance for AI coding agents (Claude Code, Cursor, etc.) and humans working on
this repo — especially when running it on **macOS**, since it was primarily
developed on **Windows**.

## What this project is

A **local AI workbench**: a FastAPI backend + a Vite/React (TypeScript) frontend
that together provide a chat / code-editor / agent / image-generation UI wired to
**local** model servers (Ollama, ComfyUI). Everything binds to `127.0.0.1` only —
it is a local-first tool, never exposed to a network.

- **Backend** — FastAPI + uvicorn on `http://127.0.0.1:8010`, SQLite via
  `aiosqlite`. Source in [`backend/app`](backend/app). Config is centralized in
  [`backend/app/config.py`](backend/app/config.py) (ports, model names, paths —
  change them there and nowhere else, most are env-overridable).
- **Frontend** — React 18 + Vite 5 + Tailwind + Monaco editor + xterm terminal on
  `http://127.0.0.1:5173`. Source in [`frontend/src`](frontend/src).
- **External services it talks to** (optional, must be running for those features):
  Ollama at `:11434`, ComfyUI at `:8188`.

## Repo layout

```
backend/            FastAPI app (Python 3.11)
  app/config.py     single source of truth: ports, models, paths, shell
  app/main.py       app factory + router wiring
  app/routers/      HTTP + WebSocket endpoints (chat, agents, run, files, ...)
  app/services/     business logic (runner, sandbox, ollama, comfy, ...)
  app/tests/        pytest suite (82+ tests)
  requirements.txt  Python deps
frontend/           Vite/React/TS SPA
  src/              components, stores (zustand), api client
Makefile            `make dev` / `make setup` / `make test`  (macOS/Linux)
dev.ps1             Windows-only launcher (PowerShell) — DO NOT use on macOS
workspace/          user projects live here (gitignored)
templates/          Build-tab webapp base template
workflows/          ComfyUI workflow JSON
```

Gitignored (so a fresh clone has none of these — you must generate them):
`backend/.venv/`, `frontend/node_modules/`, `backend/*.db`, `workspace/`.

## Running on macOS

Do **not** run `dev.ps1` (it is PowerShell). Use the Makefile. Requires Python
3.11, Node 18+, and GNU make (preinstalled with Xcode command line tools).

```bash
# one-time setup — creates the venv and installs both sides
make setup
#   equivalently, by hand:
#   cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
#   cd frontend && npm install

# run both servers together (backend :8010, frontend :5173)
make dev

# run backend tests
make test        # or: cd backend && python3 -m pytest
```

Then open <http://127.0.0.1:5173>.

> The committed venv lives at `backend/.venv/Scripts/` on Windows but must be
> `backend/.venv/bin/` on macOS. **Never copy a Windows `.venv` to a Mac** —
> recreate it with `python3 -m venv`. The venv is gitignored, so a clean `git
> clone` is fine; a folder copied off a Windows machine is not.

## Running on Windows (for reference)

```powershell
# setup
cd backend; py -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
cd ..\frontend; npm install
# run
.\dev.ps1
```

## Platform differences — READ THIS if a feature "works on Windows but not Mac"

Most of the app is cross-platform. The known platform-specific spots:

1. **Interactive Terminal is currently Windows-only.** ⚠️ This is the #1 thing
   that "doesn't work on Mac." The `/ws/terminal` WebSocket in
   [`backend/app/routers/run.py`](backend/app/routers/run.py) hard-imports
   `winpty` (the `pywinpty` package). `pywinpty` only installs on Windows
   (see the `sys_platform == "win32"` marker in
   [`requirements.txt`](backend/requirements.txt)). On macOS the import fails and
   the terminal returns the error *"Interactive terminal requires pywinpty
   (Windows)."* — the Terminal tab will not function.
   - The intended shell for macOS is already set (`/bin/zsh -l` in
     [`config.py`](backend/app/config.py) `TERMINAL_SHELL`), so only the PTY
     backend is missing.
   - **To add Mac support:** branch on `sys.platform` in `ws_terminal` and use
     the `ptyprocess` package (or the stdlib `pty`/`os.openpty` + `select`) on
     non-Windows instead of `winpty.PtyProcess`. Add `ptyprocess>=0.7;
     sys_platform != "win32"` to `requirements.txt`. The `PtyProcess` API from
     `ptyprocess` is nearly drop-in for the winpty one used here
     (`spawn`, `read`, `write`, `setwinsize`).

2. **Everything else already guards for the platform** and works on macOS:
   - Shell selection — `config.TERMINAL_SHELL` picks PowerShell on Windows, zsh
     elsewhere.
   - Non-interactive process runner —
     [`services/runner.py`](backend/app/services/runner.py) only sets Windows
     `CREATE_NEW_PROCESS_GROUP` when `_IS_WIN`; uses plain POSIX process groups
     otherwise.
   - Sandbox command matching —
     [`services/sandbox.py`](backend/app/services/sandbox.py) strips a trailing
     `.exe` before matching, so deny-list rules work on both.
   - One test (`test_runner.py`) is `skipif` Windows-only; the rest are portable.

3. **`--reload` note (Windows):** `dev.ps1` deliberately omits uvicorn
   `--reload` on Windows (Proactor vs Selector event-loop / subprocess issue —
   see the comment in `dev.ps1`). On macOS the Makefile's `backend` target *does*
   use `--reload`, which is fine there.

## Conventions for agents working here

- **Change ports / model names / paths only in
  [`backend/app/config.py`](backend/app/config.py)** — it is the single source of
  truth and most values are env-overridable (`WORKBENCH_*`).
- **Keep it local-only.** Never change the host from `127.0.0.1` to `0.0.0.0`.
- **When adding OS-specific code, branch on `sys.platform`** and keep a working
  path for both Windows and macOS/Linux rather than assuming one OS.
- **Run the tests** after backend changes: `cd backend && python3 -m pytest`
  (Windows: use `.\.venv\Scripts\python.exe -m pytest`). Type-check the frontend
  with `npm run build` (runs `tsc -b` then `vite build`).
- Default models expect **Ollama** running locally; image features expect
  **ComfyUI**. Features that call them will error clearly if those aren't up —
  that is not a platform bug.
