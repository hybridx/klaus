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
        if m.images and m.role == "user":
            parts: list[dict] = [{"type": "text", "text": m.content}]
            for img_b64 in m.images:
                data_url = (
                    img_b64 if img_b64.startswith("data:")
                    else f"data:image/jpeg;base64,{img_b64}"
                )
                parts.append({
                    "type": "image_url",
                    "image_url": data_url,
                })
            result.append(HumanMessage(content=parts))
        else:
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
        self._thinking_models: set[str] = set()

    @property
    def backend_type(self) -> str:
        return "ollama"

    def get_chat_model(
        self, model: str | None = None, temperature: float = 0.7, **kwargs
    ) -> ChatOllama:
        """Return a configured ChatOllama instance.

        Automatically enables `reasoning=True` for models whose thinking
        capability was verified by the Ollama API (via ``/api/show``).
        """
        effective_model = model or self._default_model
        if effective_model in self._thinking_models and "reasoning" not in kwargs:
            kwargs["reasoning"] = True
        return ChatOllama(
            model=effective_model,
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

    async def _inspect_model(self, model_name: str) -> dict[str, Any]:
        """Inspect a model via ``/api/show`` and return structured metadata.

        Returns a dict with:
        - capabilities: dict[str, bool] — tools, vision, thinking
        - context_length: int | None
        - parameter_count: str | None — e.g. "14B", "7B"
        - family: str | None — e.g. "qwen3", "llama"
        """
        meta: dict[str, Any] = {
            "capabilities": {"tools": False, "vision": False, "thinking": False},
            "context_length": None,
            "parameter_count": None,
            "family": None,
        }
        try:
            resp = await self._get_http().post(
                "/api/show", json={"name": model_name}
            )
            resp.raise_for_status()
            data = resp.json()

            template = data.get("template", "")
            if ".Tools" in template:
                meta["capabilities"]["tools"] = True
            if ".Think" in template:
                meta["capabilities"]["thinking"] = True

            model_info = data.get("model_info") or {}
            info_keys_lower = " ".join(model_info.keys()).lower()
            if (
                "vision" in info_keys_lower
                or "clip" in info_keys_lower
                or "projector" in info_keys_lower
            ):
                meta["capabilities"]["vision"] = True

            details = data.get("details") or {}
            meta["family"] = details.get("family")
            param_size = details.get("parameter_size")
            if param_size:
                meta["parameter_count"] = param_size

            for key, val in model_info.items():
                if "context_length" in key.lower() and isinstance(val, (int, float)):
                    meta["context_length"] = int(val)
                    break

        except Exception as exc:
            logger.debug("Failed to inspect model %s: %s", model_name, exc)

        return meta

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

            meta = await self._inspect_model(m["name"])
            detected = meta["capabilities"]

            caps = ["chat"]
            if detected["tools"]:
                caps.append("tools")
            if detected["vision"]:
                caps.append("vision")
            if detected["thinking"]:
                caps.append("thinking")
                self._thinking_models.add(m["name"])

            models.append(
                ModelInfo(
                    name=m["name"],
                    backend="ollama",
                    size=size_str,
                    quantization=details.get("quantization_level"),
                    context_length=meta["context_length"],
                    parameter_count=meta["parameter_count"],
                    family=meta["family"],
                    capabilities=caps,
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
