"""Ollama backend — wraps LangChain's ChatOllama."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from klaus.models.base import ChatMessage, GenerateRequest, GenerateResponse, ModelInfo

logger = logging.getLogger(__name__)

_ROLE_MAP = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    result = []
    for m in messages:
        cls = _ROLE_MAP.get(m.role, HumanMessage)
        result.append(cls(content=m.content))
    return result


class OllamaBackend:
    """Ollama backend powered by langchain-ollama."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model or "llama3.2"
        self._options = options or {}
        self._http: httpx.AsyncClient | None = None

    @property
    def backend_type(self) -> str:
        return "ollama"

    def get_chat_model(
        self, model: str | None = None, temperature: float = 0.7, **kwargs
    ) -> ChatOllama:
        """Return a configured ChatOllama instance.

        This is the LangChain chat model that LangGraph agents will use directly.
        """
        return ChatOllama(
            model=model or self._default_model,
            base_url=self._base_url,
            temperature=temperature,
            **kwargs,
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        llm = self.get_chat_model(
            model=request.model,
            temperature=request.temperature,
        )
        lc_messages = _to_lc_messages(request.messages)
        result = await llm.ainvoke(lc_messages)

        usage = None
        if hasattr(result, "usage_metadata") and result.usage_metadata:
            usage = {
                "prompt_tokens": result.usage_metadata.get("input_tokens"),
                "completion_tokens": result.usage_metadata.get("output_tokens"),
            }

        return GenerateResponse(
            content=result.content if isinstance(result.content, str) else str(result.content),
            model=request.model or self._default_model,
            finish_reason=(
                result.response_metadata.get("done_reason")
                if result.response_metadata else None
            ),
            usage=usage,
        )

    async def stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        llm = self.get_chat_model(
            model=request.model,
            temperature=request.temperature,
        )
        lc_messages = _to_lc_messages(request.messages)
        async for chunk in llm.astream(lc_messages):
            if chunk.content:
                yield chunk.content if isinstance(chunk.content, str) else str(chunk.content)

    async def list_models(self) -> list[ModelInfo]:
        try:
            resp = await self._get_http().get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Failed to list Ollama models: %s", exc)
            return []

        models = []
        for m in data.get("models", []):
            details = m.get("details", {})
            size_bytes = m.get("size")
            size_str = None
            if size_bytes:
                gb = size_bytes / (1024**3)
                size_str = f"{gb:.1f}GB" if gb >= 1 else f"{size_bytes / (1024**2):.0f}MB"
            models.append(
                ModelInfo(
                    name=m["name"],
                    backend="ollama",
                    size=size_str,
                    quantization=details.get("quantization_level"),
                    capabilities=["chat"],
                )
            )
        return models

    async def health(self) -> bool:
        try:
            resp = await self._get_http().get("/")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        return self._http

    async def startup(self) -> None:
        logger.info("Ollama backend (LangChain) at %s", self._base_url)

    async def shutdown(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
