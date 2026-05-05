"""Event bus — broadcasts system activity to connected SSE clients."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    CHAT_REQUEST = "chat.request"
    CHAT_RESPONSE = "chat.response"
    CHAT_TOKEN = "chat.token"
    CHAT_ERROR = "chat.error"
    CHAT_DONE = "chat.done"
    CHAT_STATUS = "chat.status"
    MODEL_ROUTED = "model.routed"
    BACKEND_HEALTH = "backend.health"
    BACKEND_REGISTERED = "backend.registered"
    BACKEND_REMOVED = "backend.removed"
    MCP_REGISTERED = "mcp.registered"
    MCP_CONNECTED = "mcp.connected"
    MCP_DISCONNECTED = "mcp.disconnected"
    MCP_REMOVED = "mcp.removed"
    MCP_TOOL_CALLED = "mcp.tool_called"
    TOOL_RESULT = "tool.result"
    SUBTASK_START = "subtask.start"
    SUBTASK_DONE = "subtask.done"
    PLAN_CREATED = "plan.created"
    PLAN_AWAITING_APPROVAL = "plan.awaiting_approval"
    PLAN_APPROVED = "plan.approved"
    PLAN_REVISED = "plan.revised"
    PLAN_REJECTED = "plan.rejected"
    PLAN_STEP_START = "plan.step_start"
    PLAN_STEP_DONE = "plan.step_done"
    PLAN_STEP_THINKING = "plan.step_thinking"
    PLAN_STEP_REFLECT = "plan.step_reflect"
    PLAN_PHASE = "plan.phase"
    PLAN_CONSOLIDATED = "plan.consolidated"
    THINKING = "thinking"
    ROUTING_RULE_SET = "routing.rule_set"
    ROUTING_RULE_REMOVED = "routing.rule_removed"


@dataclass
class Event:
    type: EventType
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"type": self.type, "data": self.data, "ts": self.timestamp}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventBus:
    """Fan-out event bus with SSE streaming.

    - System events (emit) are broadcast to ALL connected SSE clients
    - Per-session events (send_to_session) target a specific session's queue
    - Keeps a rolling history for clients that connect late
    """

    MAX_HISTORY = 200

    def __init__(self) -> None:
        self._sse_clients: dict[str, asyncio.Queue[Event]] = {}
        self._history: deque[Event] = deque(maxlen=self.MAX_HISTORY)

    def emit(self, event_type: EventType, data: dict | None = None) -> None:
        """Broadcast an event to ALL connected SSE clients."""
        event = Event(type=event_type, data=data or {})
        self._history.append(event)

        dead: list[str] = []
        for sid, q in self._sse_clients.items():
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(sid)
        for sid in dead:
            self._sse_clients.pop(sid, None)

    async def send_to_session(
        self, session_id: str, event_type: EventType, data: dict,
    ) -> None:
        """Send an event to a specific session's SSE stream (e.g. chat tokens)."""
        event = Event(type=event_type, data=data)
        q = self._sse_clients.get(session_id)
        if q is not None:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for session %s, dropping event", session_id)

    def add_sse(self, session_id: str) -> asyncio.Queue[Event]:
        """Register an SSE client and return its event queue."""
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=512)
        self._sse_clients[session_id] = q
        logger.debug("SSE client connected: %s (%d total)", session_id, len(self._sse_clients))
        return q

    def remove_sse(self, session_id: str) -> None:
        """Unregister an SSE client."""
        self._sse_clients.pop(session_id, None)
        logger.debug("SSE client disconnected: %s (%d total)", session_id, len(self._sse_clients))

    def recent(self, n: int = 50) -> list[dict]:
        events = list(self._history)[-n:]
        return [e.to_dict() for e in events]

    @property
    def subscriber_count(self) -> int:
        return len(self._sse_clients)
