"""Chat endpoint — REST API backed by the LangGraph agent."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from klaus.api.deps import get_state
from klaus.events.bus import EventType
from klaus.models.base import ChatMessage

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    messages: list[dict[str, str]] = Field(
        ..., description="List of {role, content} message dicts"
    )
    model: str | None = Field(default=None, description="Model name (uses default if omitted)")
    backend: str | None = Field(
        default=None, description="Backend name (uses routing if omitted)"
    )
    task: str | None = Field(
        default=None,
        description="Task category for routing (e.g. 'chat', 'coding', 'summarization')",
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    content: str
    model: str | None
    backend: str
    routing_reason: str


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    state = get_state()

    decision = state.task_router.resolve(
        task=req.task,
        requested_backend=req.backend,
        requested_model=req.model,
    )

    state.event_bus.emit(
        EventType.MODEL_ROUTED,
        {
            "backend": decision.backend,
            "model": decision.model,
            "task": decision.task,
            "reason": decision.reason,
        },
    )

    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in req.messages]

    state.event_bus.emit(
        EventType.CHAT_REQUEST,
        {"backend": decision.backend, "model": decision.model, "task": req.task},
    )

    try:
        if state.agent is None:
            state.init_agent()

        result = await state.agent.invoke(
            messages=messages,
            backend=decision.backend,
            model=decision.model,
            temperature=req.temperature,
            metadata={"task": req.task},
        )
    except KeyError as exc:
        state.event_bus.emit(EventType.CHAT_ERROR, {"error": str(exc)})
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        state.event_bus.emit(EventType.CHAT_ERROR, {"error": str(exc)})
        raise HTTPException(
            status_code=502, detail=f"Agent error: {exc}"
        ) from exc

    state.event_bus.emit(
        EventType.CHAT_RESPONSE,
        {"backend": decision.backend, "model": decision.model},
    )

    return ChatResponse(
        content=result["content"],
        model=result.get("model"),
        backend=decision.backend,
        routing_reason=decision.reason,
    )
