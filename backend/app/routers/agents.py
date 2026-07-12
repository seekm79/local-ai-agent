"""Agent pipeline: start/status/cancel + /ws/agents event stream (Phase 4)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .. import config, crud
from ..services.pipeline import pipeline

router = APIRouter()


class StartRun(BaseModel):
    project_id: int
    goal: str
    model: str | None = None
    helper_model: str | None = None
    max_iterations: int = config.AGENT_MAX_FIX_ITERATIONS
    halt_on_fail: bool = False
    # "single" = Phase-4 plan-once pipeline; "orchestrated" = Phase-10 backlog +
    # ReAct worker loop (for large, multi-module goals).
    strategy: str = "single"
    # Per-task step budget for the orchestrated worker loop.
    max_steps: int = config.AGENT_WORKER_MAX_STEPS


@router.post("/api/agents/start")
async def start(body: StartRun) -> dict:
    proj = crud.get_project(body.project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    if not body.goal.strip():
        raise HTTPException(400, "goal is required")

    run = crud.create_run(body.project_id, body.goal.strip())
    model = body.model or config.MODEL_PLANNER
    if "embed" in model.lower():  # embedding models can't chat — fall back
        model = config.MODEL_PLANNER

    if body.strategy == "orchestrated":
        pipeline.start_orchestrated(
            run_id=run["id"],
            project_id=body.project_id,
            goal=body.goal.strip(),
            model=model,
            helper_model=body.helper_model or config.MODEL_HELPER,
            max_steps=max(1, body.max_steps),
        )
    else:
        pipeline.start(
            run_id=run["id"],
            project_id=body.project_id,
            goal=body.goal.strip(),
            model=model,
            helper_model=body.helper_model or config.MODEL_HELPER,
            max_iterations=max(1, body.max_iterations),
            halt_on_fail=body.halt_on_fail,
        )
    return {"run_id": run["id"]}


@router.get("/api/agents/runs")
def list_runs() -> list[dict]:
    return crud.list_runs()


@router.get("/api/agents/runs/{run_id}")
def get_run(run_id: int) -> dict:
    run = crud.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {"run": run, "steps": crud.list_steps(run_id)}


class Cancel(BaseModel):
    run_id: int


@router.post("/api/agents/cancel")
def cancel(body: Cancel) -> dict:
    ok = pipeline.cancel(body.run_id)
    return {"status": "cancelling" if ok else "not_running"}


@router.websocket("/ws/agents")
async def ws_agents(ws: WebSocket) -> None:
    await ws.accept()
    q = pipeline.subscribe()
    try:
        while True:
            event = await q.get()
            await ws.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        pipeline.unsubscribe(q)
