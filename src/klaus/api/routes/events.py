"""WebSocket endpoint — bidirectional: events broadcast + agent streaming."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from klaus.api.deps import get_state
from klaus.events.bus import EventType
from klaus.models.base import ChatMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    state = get_state()
    state.event_bus.add_ws(ws)

    history = state.event_bus.recent(50)
    for event in history:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            break

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "chat":
                await _handle_chat(ws, msg, state)
            elif msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            else:
                await ws.send_text(
                    json.dumps({"type": "error", "data": {"msg": f"Unknown: {msg_type}"}})
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        state.event_bus.remove_ws(ws)


async def _handle_chat(ws: WebSocket, msg: dict, state) -> None:
    """Handle a chat message — splits multi-part requests into sub-tasks."""
    from klaus.routing.splitter import split_tasks

    messages_raw = msg.get("messages", [])
    images_raw = msg.get("images", [])
    explicit_model = msg.get("model")
    explicit_backend = msg.get("backend")
    temperature = msg.get("temperature", 0.7)
    chat_id = msg.get("id", "")

    for m in messages_raw:
        await state.db.save_message(chat_id, m["role"], m["content"])

    if state.agent is None:
        state.init_agent()

    user_text = " ".join(
        m.get("content", "") for m in messages_raw if m.get("role") == "user"
    )

    subtasks = split_tasks("") if explicit_backend else split_tasks(user_text)

    is_multi = len(subtasks) > 1

    for st in subtasks:
        task = st.task_type
        if explicit_backend:
            decision = state.task_router.resolve(
                task=task,
                requested_backend=explicit_backend,
                requested_model=explicit_model,
            )
        else:
            decision = state.task_router.resolve(task=task)

        if is_multi:
            await state.event_bus.send_to_ws(
                ws,
                EventType.SUBTASK_START,
                {
                    "index": st.index,
                    "text": st.text,
                    "task": task or "general",
                    "backend": decision.backend,
                    "model": decision.model,
                    "chat_id": chat_id,
                },
            )

        await state.event_bus.send_to_ws(
            ws,
            EventType.MODEL_ROUTED,
            {
                "backend": decision.backend,
                "model": decision.model,
                "reason": decision.reason,
                "chat_id": chat_id,
            },
        )
        state.event_bus.emit(
            EventType.MODEL_ROUTED,
            {
                "backend": decision.backend,
                "model": decision.model,
                "task": task,
                "reason": decision.reason,
                "chat_id": chat_id,
            },
        )

        sub_messages = []
        for m in messages_raw:
            cm = ChatMessage(role=m["role"], content=m["content"])
            if m["role"] == "user" and images_raw:
                cm.images = images_raw
            sub_messages.append(cm)
        if is_multi:
            sub_messages[-1] = ChatMessage(role="user", content=st.text)

        state.event_bus.emit(
            EventType.CHAT_REQUEST,
            {"backend": decision.backend, "model": decision.model, "chat_id": chat_id},
        )

        try:
            response = await _stream_subtask(
                ws, state, sub_messages, decision, temperature, chat_id, task,
            )
            if response:
                await state.db.save_message(
                    chat_id, "assistant", response,
                    model=decision.model, backend=decision.backend,
                )
            state.event_bus.emit(
                EventType.CHAT_RESPONSE,
                {
                    "backend": decision.backend,
                    "model": decision.model,
                    "chat_id": chat_id,
                    "streamed": True,
                },
            )
        except Exception as exc:
            logger.error("Agent streaming error: %s", exc)
            await state.event_bus.send_to_ws(
                ws, EventType.CHAT_ERROR, {"error": str(exc), "chat_id": chat_id}
            )
            state.event_bus.emit(
                EventType.CHAT_ERROR, {"error": str(exc), "chat_id": chat_id}
            )

        if is_multi:
            await state.event_bus.send_to_ws(
                ws,
                EventType.SUBTASK_DONE,
                {"index": st.index, "chat_id": chat_id},
            )

    await state.event_bus.send_to_ws(
        ws, EventType.CHAT_DONE, {"chat_id": chat_id}
    )


async def _stream_subtask(
    ws: WebSocket, state, messages, decision, temperature, chat_id, task,
) -> str:
    """Run agent for a single sub-task and stream events back. Returns full text."""
    full_response = ""

    async for event in state.agent.stream(
        messages=messages,
        backend=decision.backend,
        model=decision.model,
        temperature=temperature,
        metadata={"chat_id": chat_id, "task": task},
    ):
        if event["type"] == "token":
            full_response += event["content"]
            await state.event_bus.send_to_ws(
                ws, EventType.CHAT_TOKEN, {"token": event["content"], "chat_id": chat_id}
            )
        elif event["type"] == "tool_call":
            await state.event_bus.send_to_ws(
                ws,
                EventType.MCP_TOOL_CALLED,
                {"name": event["name"], "args": event["args"], "chat_id": chat_id},
            )
            state.event_bus.emit(
                EventType.MCP_TOOL_CALLED,
                {"name": event["name"], "chat_id": chat_id},
            )
        elif event["type"] == "tool_result":
            await state.event_bus.send_to_ws(
                ws,
                EventType.TOOL_RESULT,
                {
                    "name": event["name"],
                    "content": event["content"],
                    "chat_id": chat_id,
                },
            )

    return full_response


@router.get("/history")
async def event_history(n: int = 50):
    """Recent event history (for REST clients)."""
    state = get_state()
    return {"events": state.event_bus.recent(n)}
