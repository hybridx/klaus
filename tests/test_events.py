"""Tests for the event bus."""

from __future__ import annotations

import asyncio

import pytest

from klaus.events.bus import Event, EventBus, EventType


class TestEventBus:
    def test_emit_adds_to_history(self):
        bus = EventBus()
        bus.emit(EventType.BACKEND_REGISTERED, {"name": "ollama"})
        recent = bus.recent(10)
        assert len(recent) == 1
        assert recent[0]["type"] == EventType.BACKEND_REGISTERED

    def test_history_limited(self):
        bus = EventBus()
        for i in range(EventBus.MAX_HISTORY + 50):
            bus.emit(EventType.BACKEND_HEALTH, {"i": i})
        assert len(bus.recent(999)) == EventBus.MAX_HISTORY

    def test_subscriber_count_starts_at_zero(self):
        bus = EventBus()
        assert bus.subscriber_count == 0

    def test_add_sse_returns_queue(self):
        bus = EventBus()
        q = bus.add_sse("session-1")
        assert isinstance(q, asyncio.Queue)
        assert bus.subscriber_count == 1

    def test_remove_sse(self):
        bus = EventBus()
        bus.add_sse("session-1")
        bus.add_sse("session-2")
        assert bus.subscriber_count == 2
        bus.remove_sse("session-1")
        assert bus.subscriber_count == 1
        bus.remove_sse("nonexistent")
        assert bus.subscriber_count == 1

    def test_emit_broadcasts_to_all_sse_clients(self):
        bus = EventBus()
        q1 = bus.add_sse("s1")
        q2 = bus.add_sse("s2")
        bus.emit(EventType.CHAT_REQUEST, {"msg": "hello"})
        assert not q1.empty()
        assert not q2.empty()
        e1 = q1.get_nowait()
        e2 = q2.get_nowait()
        assert e1.type == EventType.CHAT_REQUEST
        assert e2.type == EventType.CHAT_REQUEST

    @pytest.mark.asyncio
    async def test_send_to_session_targets_specific_client(self):
        bus = EventBus()
        q1 = bus.add_sse("s1")
        q2 = bus.add_sse("s2")
        await bus.send_to_session("s1", EventType.CHAT_TOKEN, {"token": "hi"})
        assert not q1.empty()
        assert q2.empty()
        event = q1.get_nowait()
        assert event.type == EventType.CHAT_TOKEN
        assert event.data["token"] == "hi"

    @pytest.mark.asyncio
    async def test_send_to_session_nonexistent_is_noop(self):
        bus = EventBus()
        await bus.send_to_session("ghost", EventType.CHAT_TOKEN, {"token": "x"})


class TestEvent:
    def test_to_dict(self):
        event = Event(type=EventType.CHAT_REQUEST, data={"msg": "hello"})
        d = event.to_dict()
        assert d["type"] == "chat.request"
        assert d["data"]["msg"] == "hello"
        assert "ts" in d

    def test_to_json(self):
        event = Event(type=EventType.CHAT_RESPONSE, data={})
        j = event.to_json()
        assert '"chat.response"' in j
