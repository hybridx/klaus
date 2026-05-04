"""Event bus — broadcasts system activity to connected WebSocket clients."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    CHAT_REQUEST = "chat.request"
    CHAT_RESPONSE = "chat.response"
    CHAT_TOKEN = "chat.token"
    CHAT_ERROR = "chat.error"
    CHAT_DONE = "chat.done"
    MODEL_ROUTED = "model.routed"
    BACKEND_HEALTH = "backend.health"
    BACKEND_REGISTERED = "backend.registered"
    BACKEND_REMOVED = "backend.removed"
    MCP_REGISTERED = "mcp.registered"
    MCP_CONNECTED = "mcp.connected"
    MCP_DISCONNECTED = "mcp.disconnected"
    MCP_REMOVED = "mcp.removed"
    MCP_TOOL_CALLED = "mcp.tool_called"
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
    """Fan-out event bus with WebSocket broadcast.

    - System events are broadcast to all connected WS clients
    - Keeps a rolling history for clients that connect late
    - Supports targeted sends for per-client streams (chat tokens)
    """

    MAX_HISTORY = 200

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._ws_clients: set[WebSocket] = set()
        self._history: deque[Event] = deque(maxlen=self.MAX_HISTORY)

    def emit(self, event_type: EventType, data: dict | None = None) -> None:
        event = Event(type=event_type, data=data or {})
        self._history.append(event)

        dead_queues: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(q)
        for q in dead_queues:
            self._subscribers.remove(q)

        self._broadcast_ws(event)

    def _broadcast_ws(self, event: Event) -> None:
        if not self._ws_clients:
            return
        msg = event.to_json()
        dead: set[WebSocket] = set()
        for ws in self._ws_clients:
            try:
                asyncio.get_event_loop().create_task(self._ws_send(ws, msg, dead))
            except RuntimeError:
                dead.add(ws)
        self._ws_clients -= dead

    @staticmethod
    async def _ws_send(ws: WebSocket, msg: str, dead: set[WebSocket]) -> None:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)

    def add_ws(self, ws: WebSocket) -> None:
        self._ws_clients.add(ws)
        logger.debug("WebSocket client connected (%d total)", len(self._ws_clients))

    def remove_ws(self, ws: WebSocket) -> None:
        self._ws_clients.discard(ws)
        logger.debug("WebSocket client disconnected (%d total)", len(self._ws_clients))

    async def send_to_ws(self, ws: WebSocket, event_type: EventType, data: dict) -> None:
        """Send an event to a specific WebSocket client (e.g. chat tokens)."""
        event = Event(type=event_type, data=data)
        try:
            await ws.send_text(event.to_json())
        except Exception:
            self.remove_ws(ws)

    async def subscribe(self) -> AsyncIterator[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            self._subscribers.remove(q)

    def recent(self, n: int = 50) -> list[dict]:
        events = list(self._history)[-n:]
        return [asdict(e) for e in events]

    @property
    def subscriber_count(self) -> int:
        return len(self._ws_clients)
