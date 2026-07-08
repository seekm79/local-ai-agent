"""ComfyUI proxy endpoints + /ws/comfy progress stream (Phase 6)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .. import config
from ..services import comfy

router = APIRouter()


class _Broker:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def emit(self, type_: str, payload: dict) -> None:
        for q in list(self._subs):
            q.put_nowait({"type": type_, "payload": payload})


broker = _Broker()


@router.get("/api/comfy/status")
async def status() -> dict:
    online, err = await comfy.check_online()
    return {"online": online, "error": err, "url": config.COMFY_BASE_URL}


@router.get("/api/comfy/workflows")
def workflows() -> list[dict]:
    return comfy.list_workflows()


class GenBody(BaseModel):
    project_id: int
    workflow: str
    params: dict


@router.post("/api/comfy/generate")
async def generate(body: GenBody) -> dict:
    async def on_event(type_: str, payload: dict) -> None:
        broker.emit(type_, payload)

    broker.emit("started", {"workflow": body.workflow})
    asyncio.create_task(
        comfy.generate(body.project_id, body.workflow, body.params, on_event)
    )
    return {"status": "started"}


@router.websocket("/ws/comfy")
async def ws_comfy(ws: WebSocket) -> None:
    await ws.accept()
    q = broker.subscribe()
    try:
        while True:
            event = await q.get()
            await ws.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        broker.unsubscribe(q)
