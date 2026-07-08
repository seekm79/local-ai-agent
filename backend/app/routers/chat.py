"""Chat: WebSocket streaming at /ws/chat + REST history endpoints.

WS envelopes are typed {"type": ..., "payload": {...}} (Global rule 6).

Client -> server:
  {type:"user_message", chat_id, content, model, think}
  {type:"regenerate",   chat_id, model, think}          # redo last answer
  {type:"edit_resend",  chat_id, message_id, content, model, think}
  {type:"stop"}                                          # cancel current gen

Server -> client:
  {type:"start",          payload:{message_id}}
  {type:"reasoning_delta",payload:{content}}
  {type:"delta",          payload:{content}}
  {type:"done",           payload:{message_id, usage}}
  {type:"stopped",        payload:{message_id}}
  {type:"chat_titled",    payload:{chat_id, title}}
  {type:"error",          payload:{message}}
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .. import config, crud
from ..services import condense, ollama, rules, sandbox
from ..services.sandbox import SandboxError

router = APIRouter()


# --- REST history ------------------------------------------------------------
class ChatCreate(BaseModel):
    title: str = "New chat"
    project_id: int | None = None


class ChatPatch(BaseModel):
    title: str


@router.get("/api/chats")
async def get_chats() -> list[dict]:
    return crud.list_chats()


@router.post("/api/chats")
async def post_chat(body: ChatCreate) -> dict:
    return crud.create_chat(body.title, body.project_id)


@router.get("/api/chats/{chat_id}/messages")
async def get_messages(chat_id: int) -> list[dict]:
    return crud.list_messages(chat_id)


@router.patch("/api/chats/{chat_id}")
async def patch_chat(chat_id: int, body: ChatPatch) -> dict:
    crud.rename_chat(chat_id, body.title)
    return {"status": "ok"}


@router.delete("/api/chats/{chat_id}")
async def del_chat(chat_id: int) -> dict:
    crud.delete_chat(chat_id)
    return {"status": "ok"}


# --- WebSocket streaming -----------------------------------------------------
async def _send(ws: WebSocket, type_: str, payload: dict) -> None:
    await ws.send_json({"type": type_, "payload": payload})


def _coding_context(project_id: int, file_path: str) -> str | None:
    """Build a system message embedding the open file (path + content, truncated
    to CONTEXT_CHAR_BUDGET). Path is sandbox-validated before reading."""
    proj = crud.get_project(project_id)
    if not proj:
        return None
    try:
        target = sandbox.resolve_safe(Path(proj["path"]), file_path)
    except SandboxError:
        return None
    if not target.is_file():
        return None
    try:
        content = target.read_text(encoding="utf-8")
    except Exception:
        return None
    budget = config.CONTEXT_CHAR_BUDGET
    body = content[:budget]
    note = "" if len(content) <= budget else f"\n[...truncated to {budget} chars]"
    return (
        "You are a coding assistant inside the Workbench editor. The user is "
        f"editing this file:\n\nFile: {file_path}\n\n```\n{body}{note}\n```\n\n"
        "When proposing edits, return the FULL updated file contents in a single "
        "fenced code block so it can be applied directly to the editor."
    )


def _autotitle(chat_id: int, content: str) -> str | None:
    """Give a still-default chat a title from its first user message."""
    chat = crud.get_chat(chat_id)
    if not chat or chat["title"] != "New chat":
        return None
    title = " ".join(content.strip().split())[:48] or "New chat"
    crud.rename_chat(chat_id, title)
    return title


async def _generate(ws: WebSocket, req: dict) -> None:
    """Run one generation. Designed to be cancelled by a concurrent 'stop'."""
    content_acc: list[str] = []
    reasoning_acc: list[str] = []
    assistant: dict | None = None
    try:
        mtype = req["type"]
        chat_id = int(req["chat_id"])
        model = req["model"]
        think = bool(req.get("think"))

        if mtype == "user_message":
            crud.add_message(chat_id, "user", req["content"])
            title = _autotitle(chat_id, req["content"])
            if title:
                await _send(ws, "chat_titled", {"chat_id": chat_id, "title": title})
        elif mtype == "edit_resend":
            # Replace the edited user message and drop everything after it.
            crud.delete_messages_from(chat_id, int(req["message_id"]))
            crud.add_message(chat_id, "user", req["content"])
        elif mtype == "regenerate":
            last = crud.last_message(chat_id, "assistant")
            if last:
                crud.delete_message(last["id"])

        history = crud.list_messages(chat_id)
        msgs = [
            {"role": m["role"], "content": m["content"]}
            for m in history
            if m["role"] in ("user", "assistant", "system") and m["content"]
        ]

        # Coding mode: inject the open file as system context and use coding
        # sampling params (Global rules 9 & 10).
        temperature = config.CHAT_TEMPERATURE
        top_p: float | None = None
        project_id = req.get("project_id")
        file_path = req.get("file_path")
        system_blocks: list[str] = []
        if project_id:
            # Read-first project rules / AGENTS.md (8.7).
            rule_text = rules.load_rules(int(project_id))
            if rule_text:
                system_blocks.append(rule_text)
        if project_id and file_path:
            ctx = _coding_context(int(project_id), str(file_path))
            if ctx:
                system_blocks.append(ctx)
                temperature = config.CODING_TEMPERATURE
                top_p = config.CODING_TOP_P
        if system_blocks:
            msgs = [{"role": "system", "content": "\n\n".join(system_blocks)}, *msgs]

        # Context condensing (8.6): summarize old exchanges if the thread is large.
        msgs, condensed = await condense.maybe_condense(msgs, config.MODEL_HELPER)
        if condensed:
            await _send(ws, "condensed", {"summary": condensed})

        assistant = crud.add_message(chat_id, "assistant", "", None, model, None)
        await _send(ws, "start", {"message_id": assistant["id"]})

        usage: dict | None = None
        async for kind, data in ollama.stream_chat(
            model=model,
            messages=msgs,
            temperature=temperature,
            top_p=top_p,
            think=think,
        ):
            if kind == "delta":
                content_acc.append(str(data))
                await _send(ws, "delta", {"content": data})
            elif kind == "reasoning_delta":
                reasoning_acc.append(str(data))
                await _send(ws, "reasoning_delta", {"content": data})
            elif kind == "done":
                usage = data  # type: ignore[assignment]

        content = "".join(content_acc)
        reasoning = "".join(reasoning_acc) or None
        tokens = usage.get("completion_tokens") if usage else None
        crud.update_message(assistant["id"], content, reasoning, tokens)
        await _send(ws, "done", {"message_id": assistant["id"], "usage": usage})

    except asyncio.CancelledError:
        # User pressed stop — persist whatever streamed so far.
        if assistant is not None:
            crud.update_message(
                assistant["id"],
                "".join(content_acc),
                "".join(reasoning_acc) or None,
                None,
            )
            try:
                await _send(ws, "stopped", {"message_id": assistant["id"]})
            except Exception:
                pass
        return
    except Exception as exc:  # surface the real error (Global rule 7)
        try:
            await _send(ws, "error", {"message": f"{type(exc).__name__}: {exc}"})
        except Exception:
            pass


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    gen_task: asyncio.Task | None = None
    try:
        while True:
            req = await ws.receive_json()
            mtype = req.get("type")

            if mtype == "stop":
                if gen_task and not gen_task.done():
                    gen_task.cancel()
                continue

            if mtype in ("user_message", "regenerate", "edit_resend"):
                # One generation at a time per socket — cancel any in flight.
                if gen_task and not gen_task.done():
                    gen_task.cancel()
                gen_task = asyncio.create_task(_generate(ws, req))
            else:
                await _send(ws, "error", {"message": f"unknown type: {mtype}"})
    except WebSocketDisconnect:
        if gen_task and not gen_task.done():
            gen_task.cancel()
