"""SSE streaming + REST endpoints for chat and plan actions."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from klaus.api.deps import get_state
from klaus.events.bus import EventType
from klaus.models.base import ChatMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


# ── SSE streaming endpoint ──────────────────────────────────────────────────


@router.get("/stream")
async def sse_stream(request: Request, session_id: str = Query(...)):
    """Server-Sent Events stream for a given session.

    On connect, replays the last 50 history events, then streams live events.
    """
    state = get_state()
    queue = state.event_bus.add_sse(session_id)

    async def event_generator():
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
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            state.event_bus.remove_sse(session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── REST: send a chat message ───────────────────────────────────────────────


class ChatSendRequest(BaseModel):
    messages: list[dict[str, str]]
    images: list[str] = Field(default_factory=list)
    model: str | None = None
    backend: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    id: str = Field(default="", description="Chat/session ID")
    retry: bool = False


class ChatSendResponse(BaseModel):
    status: str = "ok"
    chat_id: str


@router.post("/chat/send", response_model=ChatSendResponse)
async def chat_send(req: ChatSendRequest, background_tasks: BackgroundTasks):
    """Accept a chat message and start streaming the response via SSE."""
    state = get_state()
    session_id = req.id or "default"

    background_tasks.add_task(
        _handle_chat, session_id, req.model_dump(), state,
    )

    return ChatSendResponse(chat_id=session_id)


# ── REST: plan approval/rejection/edit ───────────────────────────────────────


class PlanActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|edit)$")
    edits: list[dict] = Field(default_factory=list)
    reason: str = ""


@router.post("/chat/{chat_id}/plan-action")
async def plan_action(chat_id: str, req: PlanActionRequest):
    """Approve, reject, or edit an orchestrator plan."""
    state = get_state()
    _handle_plan_decision(
        state,
        req.action,
        edits=req.edits if req.action == "edit" else None,
        reason=req.reason,
    )
    return {"status": "ok", "action": req.action}


# ── History (unchanged) ─────────────────────────────────────────────────────


@router.get("/history")
async def event_history(n: int = 50):
    """Recent event history (for REST clients)."""
    state = get_state()
    return {"events": state.event_bus.recent(n)}


# ── Internal helpers ─────────────────────────────────────────────────────────


async def _send_status(session_id: str, state, chat_id: str, step: str, detail: str = "") -> None:
    """Send a progress status event to the client's SSE stream."""
    await state.event_bus.send_to_session(
        session_id, EventType.CHAT_STATUS, {"step": step, "detail": detail, "chat_id": chat_id},
    )


_ACTION_VERB_RE = re.compile(
    r'\b(?:create|write|make|build|generate|tell|show|describe|explain|find|'
    r'analyze|summarize|translate|draw|code|implement|debug|fix|run|'
    r'give|list|compare|check|send|open|search|identify)\b',
    re.IGNORECASE,
)


def _is_complex(text: str, threshold: int = 2) -> bool:
    """Detect whether a message is complex enough for orchestration.

    Checks: multiple sentences, explicit multi-task markers, or 3+ distinct
    action verbs (e.g. "create X and write Y and tell me Z" → 3 verbs).
    """
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip() and len(s.strip()) > 10]
    if len(sentences) >= threshold:
        return True

    multi_markers = [
        "then", "and also", "after that", "additionally", "also", "next",
        "as well as", "plus",
    ]
    lower = text.lower()
    if any(m in lower for m in multi_markers):
        return True

    distinct_verbs = set(_ACTION_VERB_RE.findall(lower))
    if len(distinct_verbs) >= 3:
        return True

    return False


async def _find_vision_model(state, decision):
    """Fallback: search for a vision-capable model if no 'image' routing rule matched."""
    if state.model_registry.model_supports(decision.backend, decision.model, "vision"):
        return decision
    vision_model = await state.model_registry.find_capable_model(decision.backend, "vision")
    if not vision_model:
        for bname in state.model_registry.list_backends():
            if bname == decision.backend:
                continue
            vm = await state.model_registry.find_capable_model(bname, "vision")
            if vm:
                vision_model = vm
                decision.backend = bname
                break
    if vision_model:
        original = decision.model
        decision.model = vision_model
        decision.reason += f" (switched from {original}: needs vision)"
        logger.info("Image detected, switched from %s to vision model %s", original, vision_model)
    else:
        logger.warning("Image detected but no vision model found on any backend")
    return decision


async def _handle_chat(session_id: str, msg: dict, state) -> None:
    """Handle a chat message — uses orchestrator for complex requests, single-agent for simple ones."""
    from klaus.routing.splitter import split_tasks

    messages_raw = msg.get("messages", [])
    images_raw = msg.get("images", [])
    explicit_model = msg.get("model") or None
    explicit_backend = msg.get("backend") or None
    temperature = msg.get("temperature", 0.7)
    chat_id = msg.get("id", "") or session_id
    is_retry = msg.get("retry", False)

    if not is_retry:
        for m in messages_raw:
            await state.db.save_message(chat_id, m["role"], m["content"])

    if state.agent is None:
        state.init_agent()

    user_text = " ".join(
        m.get("content", "") for m in messages_raw if m.get("role") == "user"
    )

    use_orchestrator = (
        not explicit_backend
        and _is_complex(user_text)
        and state.agent._task_router is not None
    )

    if use_orchestrator:
        await _handle_orchestrated_chat(session_id, state, messages_raw, images_raw, chat_id)
        return

    # Simple (non-complex) requests with images still go through single-agent path below

    await _send_status(session_id, state, chat_id, "classifying", "Analyzing your request...")

    subtasks = split_tasks("") if explicit_backend else split_tasks(user_text)
    is_multi = len(subtasks) > 1

    if is_multi:
        await _send_status(
            session_id, state, chat_id, "splitting",
            f"Splitting into {len(subtasks)} sub-tasks",
        )
    elif subtasks[0].task_type:
        await _send_status(
            session_id, state, chat_id, "classified",
            f"Detected: {subtasks[0].task_type}",
        )

    has_images = bool(images_raw)

    for st in subtasks:
        task = st.task_type
        use_tools = True

        await _send_status(session_id, state, chat_id, "routing", "Selecting best model...")

        if has_images and not explicit_backend:
            image_decision = state.task_router.resolve(task="image")
            if image_decision.model:
                decision = image_decision
                logger.info(
                    "Image detected — using 'image' routing rule: %s on %s",
                    decision.model, decision.backend,
                )
            else:
                decision = state.task_router.resolve(task=task)
                decision = await _find_vision_model(state, decision)
            use_tools = False
            logger.info("Image present — disabling tools for direct vision analysis")
        elif explicit_backend:
            decision = state.task_router.resolve(
                task=task,
                requested_backend=explicit_backend,
                requested_model=explicit_model,
            )
        else:
            decision = state.task_router.resolve(task=task)

        if use_tools and not state.model_registry.model_supports(
            decision.backend, decision.model, "tools"
        ):
            original_model = decision.model
            fallback = await state.model_registry.find_capable_model(
                decision.backend, "tools"
            )
            if fallback:
                decision.model = fallback
                decision.reason += f" (switched from {original_model}: no tool support)"
                logger.info(
                    "Model %s lacks tool support, falling back to %s",
                    original_model, fallback,
                )
            else:
                use_tools = False
                logger.info(
                    "Model %s lacks tool support, no fallback available — running without tools",
                    original_model,
                )

        model_label = decision.model or "default"
        await _send_status(
            session_id, state, chat_id, "routed",
            f"{model_label} on {decision.backend}",
        )

        if is_multi:
            await state.event_bus.send_to_session(
                session_id,
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

        await state.event_bus.send_to_session(
            session_id,
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

        await _send_status(session_id, state, chat_id, "memory", "Searching memory for context...")

        await _send_status(session_id, state, chat_id, "generating", f"Generating with {model_label}...")

        try:
            response = await _stream_subtask(
                session_id, state, sub_messages, decision, temperature, chat_id, task,
                use_tools=use_tools,
            )
            if response:
                await _send_status(session_id, state, chat_id, "saving", "Saving to memory...")
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
            await state.event_bus.send_to_session(
                session_id, EventType.CHAT_ERROR, {"error": str(exc), "chat_id": chat_id},
            )
            state.event_bus.emit(
                EventType.CHAT_ERROR, {"error": str(exc), "chat_id": chat_id},
            )

        if is_multi:
            await state.event_bus.send_to_session(
                session_id,
                EventType.SUBTASK_DONE,
                {"index": st.index, "chat_id": chat_id},
            )

    await state.event_bus.send_to_session(
        session_id, EventType.CHAT_DONE, {"chat_id": chat_id},
    )


async def _stream_subtask(
    session_id: str, state, messages, decision, temperature, chat_id, task,
    *, use_tools: bool = True,
) -> str:
    """Run agent for a single sub-task and stream events back. Returns full text."""
    full_response = ""

    async for event in state.agent.stream(
        messages=messages,
        backend=decision.backend,
        model=decision.model,
        temperature=temperature,
        metadata={"chat_id": chat_id, "task": task},
        use_tools=use_tools,
    ):
        if event["type"] == "token":
            full_response += event["content"]
            await state.event_bus.send_to_session(
                session_id, EventType.CHAT_TOKEN, {"token": event["content"], "chat_id": chat_id},
            )
        elif event["type"] == "tool_call":
            await _send_status(
                session_id, state, chat_id, "tool",
                f"Running tool: {event['name']}",
            )
            await state.event_bus.send_to_session(
                session_id,
                EventType.MCP_TOOL_CALLED,
                {"name": event["name"], "args": event["args"], "chat_id": chat_id},
            )
            state.event_bus.emit(
                EventType.MCP_TOOL_CALLED,
                {"name": event["name"], "chat_id": chat_id},
            )
        elif event["type"] == "tool_result":
            await _send_status(
                session_id, state, chat_id, "tool_done",
                f"Tool {event['name']} completed",
            )
            await state.event_bus.send_to_session(
                session_id,
                EventType.TOOL_RESULT,
                {
                    "name": event["name"],
                    "content": event["content"],
                    "chat_id": chat_id,
                },
            )
        elif event["type"] == "thinking":
            await state.event_bus.send_to_session(
                session_id, EventType.THINKING,
                {"content": event["content"], "chat_id": chat_id},
            )

    return full_response


def _handle_plan_decision(
    state, action: str, edits: list[dict] | None = None, reason: str = "",
) -> None:
    """Forward plan approval/rejection/edit to the agent."""
    if state.agent and state.agent.handle_plan_approval(action, edits, reason):
        logger.info("Plan decision forwarded: %s", action)
    else:
        logger.warning("Plan decision '%s' received but no active orchestrator", action)


async def _handle_orchestrated_chat(
    session_id: str, state, messages_raw: list, images_raw: list, chat_id: str,
) -> None:
    """Handle complex requests using the multi-agent orchestrator."""
    sub_messages = []
    for m in messages_raw:
        cm = ChatMessage(role=m["role"], content=m["content"])
        if m["role"] == "user" and images_raw:
            cm.images = images_raw
        sub_messages.append(cm)

    full_response = ""

    async for event in state.agent.orchestrate(
        messages=sub_messages,
        metadata={"chat_id": chat_id},
    ):
        etype = event.get("type", "")

        if etype == "status":
            await _send_status(session_id, state, chat_id, event.get("step", ""), event.get("detail", ""))
        elif etype == "plan.created":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_CREATED,
                {
                    "plan": event["plan"],
                    "agents": event.get("agents", []),
                    "chat_id": chat_id,
                },
            )
        elif etype == "plan.awaiting_approval":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_AWAITING_APPROVAL,
                {"chat_id": chat_id},
            )
        elif etype == "plan.approved":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_APPROVED,
                {"chat_id": chat_id},
            )
        elif etype == "plan.rejected":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_REJECTED,
                {"reason": event.get("reason", ""), "chat_id": chat_id},
            )
        elif etype == "plan.revised":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_REVISED,
                {"plan": event["plan"], "chat_id": chat_id},
            )
        elif etype == "plan.step_start":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_STEP_START,
                {
                    "index": event["index"],
                    "description": event["description"],
                    "task_type": event.get("task_type"),
                    "agent": event.get("agent"),
                    "backend": event.get("backend"),
                    "model": event.get("model"),
                    "chat_id": chat_id,
                },
            )
        elif etype == "plan.step_done":
            step_result = event.get("result", "")
            full_response += step_result
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_STEP_DONE,
                {
                    "index": event["index"],
                    "result": step_result,
                    "result_preview": event.get("result_preview", ""),
                    "backend": event.get("backend"),
                    "model": event.get("model"),
                    "task_type": event.get("task_type"),
                    "chat_id": chat_id,
                },
            )
        elif etype == "phase":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_PHASE,
                {
                    "phase": event.get("phase"),
                    "index": event.get("index"),
                    "chat_id": chat_id,
                },
            )
        elif etype == "plan.step_thinking":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_STEP_THINKING,
                {
                    "index": event["index"],
                    "content": event.get("content", ""),
                    "chat_id": chat_id,
                },
            )
        elif etype == "plan.step_reflect":
            await state.event_bus.send_to_session(
                session_id, EventType.PLAN_STEP_REFLECT,
                {
                    "index": event["index"],
                    "passed": event.get("passed", True),
                    "reason": event.get("reason", ""),
                    "retrying": event.get("retrying", False),
                    "chat_id": chat_id,
                },
            )
        elif etype == "done":
            pass

    if full_response:
        await state.db.save_message(chat_id, "assistant", full_response)

    await state.event_bus.send_to_session(
        session_id, EventType.CHAT_DONE, {"chat_id": chat_id},
    )
