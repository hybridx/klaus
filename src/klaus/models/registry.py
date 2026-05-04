"""Model registry — manages LangChain-backed model providers."""

from __future__ import annotations

import logging
from typing import Any

from klaus.config.settings import ModelBackendConfig
from klaus.models.backends.gemini import GeminiBackend
from klaus.models.backends.ollama import OllamaBackend
from klaus.models.base import GenerateRequest, GenerateResponse, ModelInfo

logger = logging.getLogger(__name__)

BACKEND_FACTORIES: dict[str, type] = {
    "ollama": OllamaBackend,
    "gemini": GeminiBackend,
}


def _create_backend(config: ModelBackendConfig) -> Any:
    factory = BACKEND_FACTORIES.get(config.type)
    if factory is None:
        raise ValueError(
            f"Unknown backend type '{config.type}'. "
            f"Available: {list(BACKEND_FACTORIES.keys())}"
        )

    kwargs: dict[str, Any] = {"base_url": config.base_url}
    if config.default_model:
        kwargs["default_model"] = config.default_model
    if config.options:
        kwargs["options"] = config.options

    return factory(**kwargs)


class ModelRegistry:
    """Central registry for all model backends.

    Each backend exposes a `get_chat_model()` method that returns a LangChain
    BaseChatModel, which LangGraph agents use directly. The registry also
    provides backward-compatible generate/stream for the REST API.
    """

    def __init__(self) -> None:
        self._backends: dict[str, Any] = {}
        self._default_backend: str | None = None

    async def register_from_config(
        self,
        backends_config: dict[str, ModelBackendConfig],
        default: str | None = None,
    ) -> None:
        for name, cfg in backends_config.items():
            await self.register(name, _create_backend(cfg))
        if default and default in self._backends:
            self._default_backend = default

    async def register(self, name: str, backend: Any) -> None:
        if hasattr(backend, "startup"):
            await backend.startup()
        self._backends[name] = backend
        if self._default_backend is None:
            self._default_backend = name
        btype = getattr(backend, "backend_type", type(backend).__name__)
        logger.info("Registered model backend: %s (%s)", name, btype)

    async def unregister(self, name: str) -> None:
        backend = self._backends.pop(name, None)
        if backend and hasattr(backend, "shutdown"):
            await backend.shutdown()
            logger.info("Unregistered model backend: %s", name)

    def get(self, name: str | None = None) -> Any:
        key = name or self._default_backend
        if key is None or key not in self._backends:
            available = list(self._backends.keys())
            raise KeyError(f"Backend '{key}' not found. Available: {available}")
        return self._backends[key]

    def get_chat_model(self, backend: str | None = None, **kwargs):
        """Get a LangChain chat model from the named backend."""
        return self.get(backend).get_chat_model(**kwargs)

    async def generate(
        self, request: GenerateRequest, backend: str | None = None
    ) -> GenerateResponse:
        return await self.get(backend).generate(request)

    async def list_all_models(self) -> dict[str, list[ModelInfo]]:
        result: dict[str, list[ModelInfo]] = {}
        for name, b in self._backends.items():
            result[name] = await b.list_models()
        return result

    async def health_check(self) -> dict[str, bool]:
        return {name: await b.health() for name, b in self._backends.items()}

    async def shutdown_all(self) -> None:
        for name in list(self._backends):
            await self.unregister(name)

    @property
    def backend_names(self) -> list[str]:
        return list(self._backends.keys())
