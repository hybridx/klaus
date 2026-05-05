"""Tests for the model registry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from klaus.models.base import ModelInfo
from klaus.models.registry import ModelRegistry


def _make_backend(**overrides) -> MagicMock:
    """Create a mock backend that doesn't accidentally expose startup/shutdown."""
    backend = MagicMock(spec=[])
    for k, v in overrides.items():
        setattr(backend, k, v)
    return backend


@pytest.fixture()
def registry() -> ModelRegistry:
    return ModelRegistry()


class TestModelRegistry:
    async def test_register_and_get(self, registry: ModelRegistry):
        backend = _make_backend()
        await registry.register("test_backend", backend)
        assert registry.get("test_backend") is backend

    async def test_first_registered_becomes_default(self, registry: ModelRegistry):
        backend = _make_backend()
        await registry.register("first", backend)
        assert registry.get() is backend

    async def test_get_unknown_raises(self, registry: ModelRegistry):
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    async def test_unregister(self, registry: ModelRegistry):
        backend = _make_backend(shutdown=AsyncMock())
        await registry.register("removable", backend)
        await registry.unregister("removable")
        with pytest.raises(KeyError):
            registry.get("removable")

    async def test_backend_names(self, registry: ModelRegistry):
        await registry.register("a", _make_backend())
        await registry.register("b", _make_backend())
        assert set(registry.backend_names) == {"a", "b"}

    async def test_startup_called_if_present(self, registry: ModelRegistry):
        backend = _make_backend(startup=AsyncMock())
        await registry.register("with_startup", backend)
        backend.startup.assert_awaited_once()

    async def test_shutdown_all(self, registry: ModelRegistry):
        backends = [_make_backend(shutdown=AsyncMock()) for _ in range(3)]
        for i, b in enumerate(backends):
            await registry.register(f"b{i}", b)
        await registry.shutdown_all()
        for b in backends:
            b.shutdown.assert_awaited_once()
        assert registry.backend_names == []

    async def test_health_check(self, registry: ModelRegistry):
        backend = _make_backend(health=AsyncMock(return_value=True))
        await registry.register("healthy", backend)
        result = await registry.health_check()
        assert result == {"healthy": True}


class TestCapabilityAwareness:
    async def test_model_supports_with_cache(self, registry: ModelRegistry):
        backend = _make_backend(list_models=AsyncMock(return_value=[
            ModelInfo(name="qwen3:14b", backend="ollama", capabilities=["chat", "tools"]),
            ModelInfo(name="dolphin-llama3", backend="ollama", capabilities=["chat"]),
        ]))
        await registry.register("ollama", backend)
        await registry.refresh_capabilities()

        assert registry.model_supports("ollama", "qwen3:14b", "tools") is True
        assert registry.model_supports("ollama", "dolphin-llama3", "tools") is False
        assert registry.model_supports("ollama", "dolphin-llama3", "chat") is True

    async def test_model_supports_optimistic_when_unknown(self, registry: ModelRegistry):
        """Unknown models default to True (optimistic) for non-vision capabilities."""
        backend = _make_backend(list_models=AsyncMock(return_value=[]))
        await registry.register("ollama", backend)
        await registry.refresh_capabilities()

        assert registry.model_supports("ollama", "unknown-model", "tools") is True

    async def test_model_supports_pessimistic_for_vision(self, registry: ModelRegistry):
        """Unknown models default to False (pessimistic) for vision."""
        backend = _make_backend(list_models=AsyncMock(return_value=[]))
        await registry.register("ollama", backend)
        await registry.refresh_capabilities()

        assert registry.model_supports("ollama", "unknown-model", "vision") is False

    async def test_model_supports_optimistic_when_no_cache(self, registry: ModelRegistry):
        """If capabilities haven't been refreshed, default to True for tools."""
        assert registry.model_supports("ollama", "any-model", "tools") is True

    async def test_model_supports_pessimistic_vision_no_cache(self, registry: ModelRegistry):
        """If capabilities haven't been refreshed, vision defaults to False."""
        assert registry.model_supports("ollama", "any-model", "vision") is False

    async def test_find_capable_model(self, registry: ModelRegistry):
        backend = _make_backend(list_models=AsyncMock(return_value=[
            ModelInfo(name="dolphin-llama3", backend="ollama", capabilities=["chat"]),
            ModelInfo(name="qwen3:14b", backend="ollama", capabilities=["chat", "tools"]),
            ModelInfo(name="llama3.2", backend="ollama", capabilities=["chat", "tools"]),
        ]))
        await registry.register("ollama", backend)
        await registry.refresh_capabilities()

        result = await registry.find_capable_model("ollama", "tools")
        assert result in ("qwen3:14b", "llama3.2")

    async def test_find_capable_model_none_available(self, registry: ModelRegistry):
        backend = _make_backend(list_models=AsyncMock(return_value=[
            ModelInfo(name="dolphin-llama3", backend="ollama", capabilities=["chat"]),
        ]))
        await registry.register("ollama", backend)
        await registry.refresh_capabilities()

        result = await registry.find_capable_model("ollama", "tools")
        assert result is None

    async def test_unregister_clears_cache(self, registry: ModelRegistry):
        backend = _make_backend(
            shutdown=AsyncMock(),
            list_models=AsyncMock(return_value=[
                ModelInfo(name="m1", backend="b", capabilities=["chat", "tools"]),
            ]),
        )
        await registry.register("b", backend)
        await registry.refresh_capabilities()
        assert registry.model_supports("b", "m1", "tools") is True

        await registry.unregister("b")
        assert registry.model_supports("b", "m1", "tools") is True  # optimistic for tools
        assert registry.model_supports("b", "m1", "vision") is False  # pessimistic for vision

    async def test_model_supports_fuzzy_tag_match(self, registry: ModelRegistry):
        """model 'qwen3' should match cached 'qwen3:14b' by base name."""
        backend = _make_backend(list_models=AsyncMock(return_value=[
            ModelInfo(name="qwen3:14b", backend="ollama", capabilities=["chat", "tools"]),
        ]))
        await registry.register("ollama", backend)
        await registry.refresh_capabilities()

        assert registry.model_supports("ollama", "qwen3", "tools") is True
