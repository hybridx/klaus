"""Google Gemini backend — wraps LangChain's ChatGoogleGenerativeAI."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

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


class GeminiBackend:
    """Google Gemini backend powered by langchain-google-genai.

    The API key is resolved in this order:
    1. api_key passed directly (from config YAML options.api_key)
    2. GOOGLE_API_KEY environment variable (loaded from .env)
    """

    def __init__(
        self,
        base_url: str = "https://generativelanguage.googleapis.com",
        default_model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model or "gemini-2.0-flash"
        self._options = options or {}
        self._api_key = self._options.get("api_key") or os.getenv("GOOGLE_API_KEY", "")

    @property
    def backend_type(self) -> str:
        return "gemini"

    def get_chat_model(
        self, model: str | None = None, temperature: float = 0.7, **kwargs
    ) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=model or self._default_model,
            google_api_key=self._api_key,
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
            finish_reason=None,
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
        available = [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]
        return [
            ModelInfo(
                name=name,
                backend="gemini",
                capabilities=["chat", "vision", "code"],
            )
            for name in available
        ]

    async def health(self) -> bool:
        if not self._api_key:
            return False
        try:
            llm = self.get_chat_model()
            result = await llm.ainvoke([HumanMessage(content="ping")])
            return bool(result.content)
        except Exception as exc:
            logger.warning("Gemini health check failed: %s", exc)
            return False

    async def startup(self) -> None:
        if not self._api_key:
            logger.warning(
                "Gemini backend has no API key — set GOOGLE_API_KEY in .env "
                "or options.api_key in config"
            )
        else:
            logger.info(
                "Gemini backend ready (model: %s, key: %s...)",
                self._default_model,
                self._api_key[:8],
            )

    async def shutdown(self) -> None:
        pass
