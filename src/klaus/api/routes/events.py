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
    """Handle a chat message using the LangGraph agent with streaming."""
    from klaus.routing.router import classify_task

    messages_raw = msg.get("messages", [])
    images_raw = msg.get("images", [])
    task = msg.get("task")
    model = msg.get("model")
    backend = msg.get("backend")
    temperature = msg.get("temperature", 0.7)
    chat_id = msg.get("id", "")

    if not task:
        user_text = " ".join(m.get("content", "") for m in messages_raw if m.get("role") == "user")
        task = classify_task(user_text)

    decision = state.task_router.resolve(
        task=task,
        requested_backend=backend,
        requested_model=model,
    )

    state.event_bus.emit(
        EventType.MODEL_ROUTED,
        {
            "backend": decision.backend,
            "model": decision.model,
            "task": decision.task,
            "reason": decision.reason,
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

    messages = []
    for m in messages_raw:
        cm = ChatMessage(role=m["role"], content=m["content"])
        if m["role"] == "user" and images_raw:
            cm.images = images_raw
        messages.append(cm)

    for m in messages_raw:
        await state.db.save_message(chat_id, m["role"], m["content"])

    state.event_bus.emit(
        EventType.CHAT_REQUEST,
        {"backend": decision.backend, "model": decision.model, "chat_id": chat_id},
    )

    try:
        if state.agent is None:
            state.init_agent()

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
            elif event["type"] == "done":
                await state.event_bus.send_to_ws(
                    ws, EventType.CHAT_DONE, {"chat_id": chat_id}
                )

        if full_response:
            await state.db.save_message(
                chat_id, "assistant", full_response,
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


@router.get("/history")
async def event_history(n: int = 50):
    """Recent event history (for REST clients)."""
    state = get_state()
    return {"events": state.event_bus.recent(n)}
