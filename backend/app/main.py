"""FastAPI application entry point.

Binds to 127.0.0.1 only (Global rule 1). CORS is allowed for the Vite dev
server origin. Routers for later phases are registered as they are built.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .db import init_db
from .routers import agents, browser, build, chat, checkpoints, comfy, files, modes
from .routers import projects, run, search
from .routers import settings as settings_router
from .services import modes as modes_svc
from .services import ollama, settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("workbench")

app = FastAPI(title="Workbench", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(projects.router)
app.include_router(files.router)
app.include_router(run.router)
app.include_router(agents.router)
app.include_router(comfy.router)
app.include_router(checkpoints.router)
app.include_router(modes.router)
app.include_router(search.router)
app.include_router(browser.router)
app.include_router(build.router)
app.include_router(settings_router.router)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    settings.load()  # apply persisted setting overrides onto config
    modes_svc.seed_defaults()  # ensure built-in agent modes exist
    log.info("SQLite ready at %s", config.DB_PATH)
    log.info("Projects root: %s", config.PROJECTS_ROOT)
    config.PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
async def health() -> dict:
    """Health check. Returns the live model list from Ollama plus the configured
    model roles. If Ollama is unreachable we still return 200 with an error
    string and an empty list so the UI can show a clear prerequisite state."""
    models: list[str] = []
    ollama_error: str | None = None
    try:
        models = await ollama.list_models()
    except Exception as exc:  # surface the real reason (Global rule 7)
        ollama_error = f"{type(exc).__name__}: {exc}"

    return {
        "status": "ok",
        "backend_port": config.BACKEND_PORT,
        "ollama_url": config.OLLAMA_BASE_URL,
        "ollama_error": ollama_error,
        "models": models,
        "config": {
            "model_big": config.MODEL_BIG,
            "model_helper": config.MODEL_HELPER,
            "model_big_available": config.MODEL_BIG in models,
        },
    }


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.BACKEND_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
