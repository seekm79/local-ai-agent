"""Single source of truth for models, ports, and paths.

Change model names, ports, or the projects root here and nowhere else.
On Windows the projects root and DB live under the repo by default.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- Paths -------------------------------------------------------------------
# Repo root = two levels up from this file (backend/app/config.py -> repo/).
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# DEFAULT PROJECTS ROOT — all user projects live here. Overridable via env.
PROJECTS_ROOT: Path = Path(
    os.environ.get("WORKBENCH_PROJECTS_ROOT", REPO_ROOT / "workspace")
).resolve()

# SQLite database file and schema.
DB_PATH: Path = Path(
    os.environ.get("WORKBENCH_DB_PATH", REPO_ROOT / "backend" / "workbench.db")
).resolve()
SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"

# ComfyUI workflow templates (API-format JSON) live here.
WORKFLOWS_DIR: Path = REPO_ROOT / "workflows"

# Build tab (Phase 9): the immutable base template every Build project copies.
WEBAPP_TEMPLATE_DIR: Path = REPO_ROOT / "templates" / "webapp-base"
# Package manager for Build projects (bun per the template; npm is a fallback).
WEB_PACKAGE_MANAGER: str = os.environ.get("WORKBENCH_WEB_PM", "bun")

# --- Ports / hosts -----------------------------------------------------------
HOST: str = "127.0.0.1"  # NEVER bind to 0.0.0.0 — local only (Global rule 1).
BACKEND_PORT: int = int(os.environ.get("WORKBENCH_BACKEND_PORT", 8010))
FRONTEND_PORT: int = int(os.environ.get("WORKBENCH_FRONTEND_PORT", 5173))
FRONTEND_ORIGIN: str = f"http://{HOST}:{FRONTEND_PORT}"

# --- External services -------------------------------------------------------
# Ollama's OpenAI-compatible endpoint. Use the `openai` client with a dummy key.
OLLAMA_BASE_URL: str = os.environ.get(
    "WORKBENCH_OLLAMA_URL", "http://127.0.0.1:11434/v1"
)
OLLAMA_API_KEY: str = "ollama"  # dummy — Ollama ignores it.

COMFY_BASE_URL: str = os.environ.get("WORKBENCH_COMFY_URL", "http://127.0.0.1:8188")

# --- Models ------------------------------------------------------------------
# Primary/big model and small helper. Everything downstream reads these names,
# so swapping a model is a one-line change here.
# Text/coding/planning model. Use qwen3-coder:30b: it fits fully on GPU (~44 GB)
# and is fast. Do NOT default this to a vision model like qwen3-vl:32b — the text
# path uses the model's DEFAULT context (qwen3-vl: 262k ≈ 89 GB), which spills to
# CPU and stalls generation. Image interpretation is handled separately by an
# auto-selected vision model (ollama.find_vision_model, context-capped at 8k).
MODEL_BIG: str = os.environ.get("WORKBENCH_MODEL_BIG", "qwen3-coder:30b")
# Helper does summaries/commit messages — must be an *instruct* model. Defaults to
# the big model so nothing references an uninstalled tag.
MODEL_HELPER: str = os.environ.get("WORKBENCH_MODEL_HELPER", "qwen3-coder:30b")
# Embedding model for codebase semantic search (Phase 8.3).
MODEL_EMBED: str = os.environ.get("WORKBENCH_MODEL_EMBED", "nomic-embed-text")

# Pipeline role assignments (Phase 4). Default the heavy roles to the big model.
MODEL_PLANNER: str = os.environ.get("WORKBENCH_MODEL_PLANNER", MODEL_BIG)
MODEL_CODER: str = os.environ.get("WORKBENCH_MODEL_CODER", MODEL_BIG)
MODEL_REVIEWER: str = os.environ.get("WORKBENCH_MODEL_REVIEWER", MODEL_BIG)

# --- Sampling defaults -------------------------------------------------------
CHAT_TEMPERATURE: float = 0.7
CODING_TEMPERATURE: float = 0.6
CODING_TOP_P: float = 0.95

# Char budget for injecting the open file into coding-mode context (Phase 2).
CONTEXT_CHAR_BUDGET: int = 12000

# --- Terminal / runners (Phase 3) --------------------------------------------
# Interactive shell for /ws/terminal. The spec uses `zsh -l` on macOS; on
# Windows we spawn PowerShell. Overridable so users can pick pwsh/cmd/bash.
if sys.platform == "win32":
    TERMINAL_SHELL: list[str] = ["powershell.exe", "-NoLogo"]
else:
    TERMINAL_SHELL = ["/bin/zsh", "-l"]

# Grace period before force-killing a process on stop (SIGTERM -> SIGKILL).
PROCESS_KILL_GRACE_SEC: float = 5.0

# Commands that require UI confirmation before running (Global rule 3). Editable
# in the Settings screen; sandbox.command_needs_confirmation reads this live.
DENY_COMMANDS: list[str] = [
    "rm", "rmdir", "del", "sudo", "chmod", "chown", "mkfs", "dd",
]

# --- Agent pipeline (Phase 4) ------------------------------------------------
# Max reviewer<->coder fix iterations per code step before it's marked failed.
AGENT_MAX_FIX_ITERATIONS: int = 3
# Max rounds of JSON re-prompting when the planner emits unparseable JSON.
AGENT_PLAN_RETRIES: int = 2
# Orchestrated strategy (Phase 10): max ReAct loop turns a worker gets per task
# before the task is marked failed. Each turn is one tool action.
AGENT_WORKER_MAX_STEPS: int = 20
# Timeout for a single reviewer/coder command (seconds).
AGENT_COMMAND_TIMEOUT: float = 240.0

# Context condensing (Phase 8.6): when a conversation's estimated size exceeds
# this many characters (~4 chars/token), summarize the oldest exchanges into a
# compact memory block. Never condense system messages or the most recent N.
CONDENSE_CHAR_THRESHOLD: int = 24000
CONDENSE_KEEP_RECENT: int = 4
