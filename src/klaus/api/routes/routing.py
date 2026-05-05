"""Task routing management endpoints — CRUD for routing rules."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from klaus.api.deps import get_state
from klaus.events.bus import EventType
from klaus.routing.router import check_keyword_overlap

router = APIRouter(prefix="/routing", tags=["routing"])


def _check_keyword_overlap(state, task: str, keywords: list[str]) -> str | None:
    """Check new keywords against all existing rules for overlap."""
    existing = {
        t: r.keywords for t, r in state.task_router.get_rules().items()
        if r.keywords
    }
    return check_keyword_overlap(existing, task, keywords)


class SetRuleRequest(BaseModel):
    task: str
    preferred_backend: str | None = Field(default=None)
    preferred_model: str | None = Field(default=None)
    fallback_backends: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    description: str = Field(default="")
    max_tokens: int | None = Field(default=None)
    temperature: float | None = Field(default=None)


@router.get("/rules")
async def list_rules():
    state = get_state()
    rules = state.task_router.get_rules()
    return {
        "rules": {
            task: {
                "preferred_backend": r.preferred_backend,
                "preferred_model": r.preferred_model,
                "fallback_backends": r.fallback_backends,
                "keywords": r.keywords,
                "description": r.description,
                "max_tokens": r.max_tokens,
                "temperature": r.temperature,
            }
            for task, r in rules.items()
        }
    }


@router.post("/rules", status_code=201)
async def set_rule(req: SetRuleRequest):
    from klaus.config.settings import TaskRoutingRule

    state = get_state()
    rule = TaskRoutingRule(
        preferred_backend=req.preferred_backend,
        preferred_model=req.preferred_model,
        fallback_backends=req.fallback_backends,
        keywords=req.keywords,
        description=req.description,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )

    conflict = _check_keyword_overlap(state, req.task, req.keywords)
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Keywords overlap >50% with existing intent '{conflict}'",
        )

    state.task_router.set_rule(req.task, rule)
    state.event_bus.emit(EventType.ROUTING_RULE_SET, {"task": req.task})
    await state.db.save_routing_rule(req.task, rule.model_dump())
    return {"task": req.task, "status": "set"}


@router.delete("/rules/{task}")
async def remove_rule(task: str):
    state = get_state()
    state.task_router.remove_rule(task)
    state.event_bus.emit(EventType.ROUTING_RULE_REMOVED, {"task": task})
    await state.db.delete_routing_rule(task)
    return {"task": task, "status": "removed"}


class UpdateRuleRequest(BaseModel):
    preferred_backend: str | None = None
    preferred_model: str | None = None
    fallback_backends: list[str] | None = None
    keywords: list[str] | None = None
    description: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@router.put("/rules/{task}")
async def update_rule(task: str, req: UpdateRuleRequest):
    """Update specific fields of an existing routing rule in-place."""
    state = get_state()
    existing = state.task_router.get_rules().get(task)
    if not existing:
        raise HTTPException(status_code=404, detail=f"No rule for '{task}'")

    data = existing.model_dump()
    update = {k: v for k, v in req.model_dump().items() if v is not None}

    if "keywords" in update and update["keywords"]:
        conflict = _check_keyword_overlap(state, task, update["keywords"])
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Keywords overlap >50% with intent '{conflict}'",
            )

    data.update(update)
    from klaus.config.settings import TaskRoutingRule

    rule = TaskRoutingRule(**data)
    state.task_router.set_rule(task, rule)
    state.event_bus.emit(EventType.ROUTING_RULE_SET, {"task": task})
    await state.db.save_routing_rule(task, rule.model_dump())
    return {"task": task, "status": "updated"}


@router.get("/resolve")
async def resolve_route(task: str | None = None):
    """Preview which backend/model would be selected for a given task."""
    state = get_state()
    decision = state.task_router.resolve(task=task)
    return {
        "backend": decision.backend,
        "model": decision.model,
        "task": decision.task,
        "reason": decision.reason,
        "fallback_used": decision.fallback_used,
    }


@router.get("/backends")
async def list_backends_with_meta():
    """List backends with locality and health metadata."""
    state = get_state()
    result = []
    health = await state.model_registry.health_check()
    for name, meta in state.task_router._backends.items():
        result.append({
            "name": meta.name,
            "locality": meta.locality,
            "healthy": health.get(name, False),
            "default_model": meta.default_model,
            "type": name,
        })
    return {"backends": result}


@router.get("/status")
async def routing_status():
    state = get_state()
    return {
        "prefer_local": state.task_router._prefer_local,
        "subscribers": state.event_bus.subscriber_count,
        "event_history_size": len(state.event_bus._history),
        "backends_registered": len(state.task_router._backends),
        "rules_count": len(state.task_router.get_rules()),
    }
