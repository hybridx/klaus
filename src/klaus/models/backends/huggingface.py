"""HuggingFace backend — wraps LangChain's ChatHuggingFace via HF Inference API."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

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
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })
            result.append(HumanMessage(content=parts))
        else:
            result.append(cls(content=m.content))
    return result


_RECOMMENDED_MODELS = [
    ("Qwen/Qwen3-235B-A22B", ["chat", "code", "reasoning"]),
    ("meta-llama/Llama-3.3-70B-Instruct", ["chat", "code"]),
    ("mistralai/Mistral-Small-24B-Instruct-2501", ["chat", "code"]),
    ("google/gemma-3-27b-it", ["chat", "vision"]),
    ("NousResearch/Hermes-3-Llama-3.1-8B", ["chat", "code"]),
    ("microsoft/Phi-4-mini-instruct", ["chat", "code"]),
]


class HuggingFaceBackend:
    """HuggingFace backend via the Inference API (serverless).

    Uses ChatHuggingFace from langchain-huggingface, which wraps
    huggingface_hub.InferenceClient under the hood. No local GPU required.

    API key resolved in this order:
    1. options.api_key from config YAML
    2. HF_TOKEN environment variable
    """

    def __init__(
        self,
        base_url: str = "https://api-inference.huggingface.co",
        default_model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model or "Qwen/Qwen3-235B-A22B"
        self._options = options or {}
        self._api_key = self._options.get("api_key") or os.getenv("HF_TOKEN", "")

    @property
    def backend_type(self) -> str:
        return "huggingface"

    def get_chat_model(
        self, model: str | None = None, temperature: float = 0.7, **kwargs
    ) -> ChatHuggingFace:
        repo_id = model or self._default_model
        llm = HuggingFaceEndpoint(
            repo_id=repo_id,
            huggingfacehub_api_token=self._api_key,
            temperature=temperature,
            task="text-generation",
        )
        return ChatHuggingFace(llm=llm)

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
        return [
            ModelInfo(
                name=name,
                backend="huggingface",
                capabilities=caps,
            )
            for name, caps in _RECOMMENDED_MODELS
        ]

    async def health(self) -> bool:
        if not self._api_key:
            return False
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(token=self._api_key)
            client.text_generation("test", model=self._default_model, max_new_tokens=1)
            return True
        except Exception as exc:
            logger.warning("HuggingFace health check failed: %s", exc)
            return False

    async def startup(self) -> None:
        if not self._api_key:
            logger.warning(
                "HuggingFace backend has no API key — set HF_TOKEN in .env "
                "or options.api_key in config"
            )
        else:
            logger.info(
                "HuggingFace backend ready (model: %s, key: %s...)",
                self._default_model,
                self._api_key[:8],
            )

    async def shutdown(self) -> None:
        pass
