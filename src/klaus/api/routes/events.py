"""SSE streaming + REST endpoints for chat and plan actions."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from klaus.api.deps import get_state
from klaus.events.bus import EventType
from klaus.models.base import ChatMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["events"])


# -- SSE stream -------------------------------------------------------------


@router.get("/stream")
async def sse_stream(request: Request, session_id: str = Query(...)):
    state = get_state()
    queue = state.event_bus.add_sse(session_id)

    async def generate():
        try:
            for evt in state.event_bus.recent(50):
                if await request.is_disconnected():
                    return
                yield f"data: {json.dumps(evt)}\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {event.to_json()}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            state.event_bus.remove_sse(session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- REST: send chat --------------------------------------------------------


class ChatSendRequest(BaseModel):
    messages: list[dict[str, str]]
    images: list[str] = Field(default_factory=list)
    model: str | None = None
    backend: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    id: str = Field(default="", description="Chat/session ID")
    retry: bool = False


@router.post("/chat/send")
async def chat_send(req: ChatSendRequest, background_tasks: BackgroundTasks):
    state = get_state()
    session_id = req.id or "default"
    background_tasks.add_task(_handle_chat, session_id, req.model_dump(), state)
    return {"status": "ok", "chat_id": session_id}


# -- REST: plan approval -----------------------------------------------------


class PlanActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|edit)$")
    edits: list[dict] = Field(default_factory=list)
    reason: str = ""


@router.post("/chat/{chat_id}/plan-action")
async def plan_action(chat_id: str, req: PlanActionRequest):
    state = get_state()
    agent = state.agent
    if agent and agent.handle_plan_approval(
        req.action, req.edits if req.action == "edit" else None, req.reason
    ):
        logger.info("Plan decision forwarded: %s", req.action)
    else:
        logger.warning("Plan decision '%s' but no active orchestrator", req.action)
    return {"status": "ok", "action": req.action}


@router.get("/history")
async def event_history(n: int = 50):
    return {"events": get_state().event_bus.recent(n)}


# -- Helpers -----------------------------------------------------------------


async def _send(session_id: str, state, event_type: EventType, data: dict) -> None:
    await state.event_bus.send_to_session(session_id, event_type, data)


async def _status(session_id: str, state, chat_id: str, step: str, detail: str = "") -> None:
    await _send(
        session_id,
        state,
        EventType.CHAT_STATUS,
        {"step": step, "detail": detail, "chat_id": chat_id},
    )


_ACTION_VERB_RE = re.compile(
    r"\b(?:create|write|make|build|generate|tell|show|describe|explain|find|"
    r"analyze|summarize|translate|draw|code|implement|debug|fix|run|"
    r"give|list|compare|check|send|open|search|identify)\b",
    re.IGNORECASE,
)


def _is_complex(text: str, threshold: int = 2) -> bool:
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip() and len(s.strip()) > 10]
    if len(sentences) >= threshold:
        return True
    multi_markers = [
        "then",
        "and also",
        "after that",
        "additionally",
        "also",
        "next",
        "as well as",
        "plus",
    ]
    lower = text.lower()
    if any(m in lower for m in multi_markers):
        return True
    return len(set(_ACTION_VERB_RE.findall(lower))) >= 3


async def _find_vision_model(state, decision):
    if state.model_registry.model_supports(decision.backend, decision.model, "vision"):
        return decision
    vm = await state.model_registry.find_capable_model(decision.backend, "vision")
    if not vm:
        for bname in state.model_registry.list_backends():
            if bname == decision.backend:
                continue
            vm = await state.model_registry.find_capable_model(bname, "vision")
            if vm:
                decision.backend = bname
                break
    if vm:
        original = decision.model
        decision.model = vm
        decision.reason += f" (switched from {original}: needs vision)"
        logger.info("Vision fallback: %s -> %s", original, vm)
    return decision


# -- Chat handler ------------------------------------------------------------


async def _handle_chat(session_id: str, msg: dict, state) -> None:
    from klaus.routing.splitter import split_tasks

    messages_raw = msg.get("messages", [])
    images_raw = msg.get("images", [])
    explicit_model = msg.get("model") or None
    explicit_backend = msg.get("backend") or None
    temperature = msg.get("temperature", 0.7)
    chat_id = msg.get("id", "") or session_id

    if not msg.get("retry", False):
        for m in messages_raw:
            await state.db.save_message(chat_id, m["role"], m["content"])

    history = await state.db.get_conversation(chat_id, limit=40)
    if len(history) > len(messages_raw):
        messages_raw = [{"role": h["role"], "content": h["content"]} for h in history]

    if state.agent is None:
        state.init_agent()

    user_text = " ".join(m.get("content", "") for m in messages_raw if m.get("role") == "user")

    if not explicit_backend and not explicit_model and _is_complex(user_text) and state.agent._task_router is not None:
        await _handle_orchestrated_chat(session_id, state, messages_raw, images_raw, chat_id)
        return

    await _status(session_id, state, chat_id, "classifying", "Analyzing your request...")

    subtasks = split_tasks("") if explicit_backend else split_tasks(user_text)
    is_multi = len(subtasks) > 1
    has_images = bool(images_raw)

    for st in subtasks:
        task = st.task_type
        use_tools = True

        await _status(session_id, state, chat_id, "routing", "Selecting best model...")

        if has_images and not explicit_backend:
            image_decision = state.task_router.resolve(task="image")
            decision = (
                image_decision if image_decision.model else state.task_router.resolve(task=task)
            )
            if not image_decision.model:
                decision = await _find_vision_model(state, decision)
            use_tools = False
        elif explicit_backend:
            decision = state.task_router.resolve(
                task=task, requested_backend=explicit_backend, requested_model=explicit_model
            )
        else:
            decision = state.task_router.resolve(task=task)

        user_forced = bool(explicit_backend)
        if use_tools and not state.model_registry.model_supports(
            decision.backend, decision.model, "tools"
        ):
            if user_forced:
                use_tools = False
            else:
                fallback = await state.model_registry.find_capable_model(
                    decision.backend, "tools"
                )
                if fallback:
                    decision.model = fallback
                else:
                    use_tools = False

        model_label = decision.model or "default"
        await _status(session_id, state, chat_id, "routed", f"{model_label} on {decision.backend}")

        if is_multi:
            await _send(
                session_id,
                state,
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

        await _send(
            session_id,
            state,
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

        sub_messages = _build_chat_messages(messages_raw, images_raw)
        if is_multi:
            sub_messages[-1] = ChatMessage(role="user", content=st.text)

        state.event_bus.emit(
            EventType.CHAT_REQUEST,
            {"backend": decision.backend, "model": decision.model, "chat_id": chat_id},
        )
        await _status(session_id, state, chat_id, "generating", f"Generating with {model_label}...")

        try:
            response = await _stream_subtask(
                session_id,
                state,
                sub_messages,
                decision,
                temperature,
                chat_id,
                task,
                use_tools=use_tools,
            )
            if response:
                await state.db.save_message(
                    chat_id, "assistant", response, model=decision.model, backend=decision.backend
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
            await _send(
                session_id, state, EventType.CHAT_ERROR, {"error": str(exc), "chat_id": chat_id}
            )

        if is_multi:
            await _send(
                session_id, state, EventType.SUBTASK_DONE, {"index": st.index, "chat_id": chat_id}
            )

    await _send(session_id, state, EventType.CHAT_DONE, {"chat_id": chat_id})


def _build_chat_messages(messages_raw: list[dict], images_raw: list[str]) -> list[ChatMessage]:
    result = []
    for m in messages_raw:
        cm = ChatMessage(role=m["role"], content=m["content"])
        if m["role"] == "user" and images_raw:
            cm.images = images_raw
        result.append(cm)
    return result


async def _stream_subtask(
    session_id, state, messages, decision, temperature, chat_id, task, *, use_tools=True
) -> str:
    full = ""
    async for event in state.agent.stream(
        messages=messages,
        backend=decision.backend,
        model=decision.model,
        temperature=temperature,
        metadata={"chat_id": chat_id, "task": task},
        use_tools=use_tools,
    ):
        t = event["type"]
        if t == "token":
            full += event["content"]
            await _send(
                session_id,
                state,
                EventType.CHAT_TOKEN,
                {"token": event["content"], "chat_id": chat_id},
            )
        elif t == "tool_call":
            await _status(session_id, state, chat_id, "tool", f"Running tool: {event['name']}")
            await _send(
                session_id,
                state,
                EventType.MCP_TOOL_CALLED,
                {"name": event["name"], "args": event["args"], "chat_id": chat_id},
            )
        elif t == "tool_result":
            await _status(
                session_id, state, chat_id, "tool_done", f"Tool {event['name']} completed"
            )
            await _send(
                session_id,
                state,
                EventType.TOOL_RESULT,
                {"name": event["name"], "content": event["content"], "chat_id": chat_id},
            )
        elif t == "thinking":
            await _send(
                session_id,
                state,
                EventType.THINKING,
                {"content": event["content"], "chat_id": chat_id},
            )
    return full


# -- Orchestrated event type → SSE mapping ----------------------------------

_ORCH_EVENT_MAP: dict[str, EventType] = {
    "plan.created": EventType.PLAN_CREATED,
    "plan.awaiting_approval": EventType.PLAN_AWAITING_APPROVAL,
    "plan.approved": EventType.PLAN_APPROVED,
    "plan.rejected": EventType.PLAN_REJECTED,
    "plan.revised": EventType.PLAN_REVISED,
    "plan.step_start": EventType.PLAN_STEP_START,
    "plan.step_done": EventType.PLAN_STEP_DONE,
    "plan.step_thinking": EventType.PLAN_STEP_THINKING,
    "plan.step_reflect": EventType.PLAN_STEP_REFLECT,
    "phase": EventType.PLAN_PHASE,
}


async def _handle_orchestrated_chat(
    session_id: str, state, messages_raw: list, images_raw: list, chat_id: str
) -> None:
    sub_messages = _build_chat_messages(messages_raw, images_raw)
    full_response = ""

    async for event in state.agent.orchestrate(
        messages=sub_messages, metadata={"chat_id": chat_id}
    ):
        etype = event.get("type", "")

        if etype == "status":
            await _status(
                session_id, state, chat_id, event.get("step", ""), event.get("detail", "")
            )
        elif etype == "done":
            pass
        elif etype in _ORCH_EVENT_MAP:
            data = {k: v for k, v in event.items() if k != "type"}
            data["chat_id"] = chat_id
            await _send(session_id, state, _ORCH_EVENT_MAP[etype], data)
            if etype == "plan.step_done":
                full_response += event.get("result", "")

    if full_response:
        await state.db.save_message(chat_id, "assistant", full_response)
    await _send(session_id, state, EventType.CHAT_DONE, {"chat_id": chat_id})
