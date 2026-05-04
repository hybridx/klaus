"""Superpower management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from klaus.api.deps import get_state

router = APIRouter(prefix="/superpowers", tags=["superpowers"])


@router.get("")
async def list_superpowers():
    state = get_state()
    if state.superpowers is None:
        return {"superpowers": []}
    return {"superpowers": state.superpowers.list_all()}


@router.get("/tools")
async def list_superpower_tools():
    """List all tools provided by active superpowers."""
    state = get_state()
    if state.superpowers is None:
        return {"tools": []}
    tools = state.superpowers.collect_tools()
    return {
        "tools": [
            {"name": t.name, "description": t.description}
            for t in tools
        ]
    }
