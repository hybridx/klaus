"""Conversation history endpoints — backed by SQLite."""

from __future__ import annotations

from fastapi import APIRouter

from klaus.api.deps import get_state

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/")
async def list_sessions(limit: int = 50):
    """List recent conversation sessions."""
    state = get_state()
    sessions = await state.db.list_sessions(limit=limit)
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_conversation(session_id: str, limit: int = 100):
    """Get message history for a conversation session."""
    state = get_state()
    messages = await state.db.get_conversation(session_id, limit=limit)
    return {"session_id": session_id, "messages": messages}
