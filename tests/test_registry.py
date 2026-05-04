"""Tests for the model registry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

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
