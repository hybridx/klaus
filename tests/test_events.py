"""Tests for the event bus."""

from __future__ import annotations

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
