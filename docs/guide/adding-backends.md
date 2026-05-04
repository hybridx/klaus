# Adding Model Backends

klaus supports multiple LLM providers through its **Model Registry**. Each provider is a backend class that wraps a LangChain chat model.

## Existing Backends

| Backend | Provider | Config type | Default model | Key feature |
|---------|----------|-------------|---------------|-------------|
| `OllamaBackend` | Ollama (local) | `ollama` | `llama3.2` | Local-first, vision |
| `GeminiBackend` | Google AI | `gemini` | `gemini-2.0-flash` | Cloud API |
| `HuggingFaceBackend` | HuggingFace Hub | `huggingface` | `Qwen/Qwen3-235B-A22B` | Inference API, vision |

## Quick Start

Three files to touch: the backend class, the registry factory map, and the config.

::: code-group

```python [src/klaus/models/backends/openai.py]
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_openai import ChatOpenAI

from klaus.models.base import (
    ChatMessage,
    GenerateRequest,
    GenerateResponse,
    ModelInfo,
)

logger = logging.getLogger(__name__)


class OpenAIBackend:
    """OpenAI-compatible backend using LangChain's ChatOpenAI."""

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str = "gpt-4o",
        options: dict[str, Any] | None = None,
    ) -> None:
        options = options or {}
        self._base_url = base_url
        self._default_model = default_model
        self._api_key = options.get("api_key") or os.getenv("OPENAI_API_KEY", "")

    @property
    def backend_type(self) -> str:
        return "openai"

    def get_chat_model(self, model=None, temperature=0.7, **kwargs):
        return ChatOpenAI(
            model=model or self._default_model,
            temperature=temperature,
            api_key=self._api_key,
            base_url=self._base_url,
            **kwargs,
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        llm = self.get_chat_model(model=request.model, temperature=request.temperature)
        lc_messages = _to_lc_messages(request.messages)
        result = await llm.ainvoke(lc_messages)
        return GenerateResponse(
            content=result.content if isinstance(result.content, str) else str(result.content),
            model=request.model or self._default_model,
        )

    async def stream(self, request: GenerateRequest):
        llm = self.get_chat_model(model=request.model, temperature=request.temperature)
        async for chunk in llm.astream(_to_lc_messages(request.messages)):
            if chunk.content:
                yield chunk.content

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(name="gpt-4o", backend="openai", capabilities=["chat", "vision"]),
            ModelInfo(name="gpt-4o-mini", backend="openai", capabilities=["chat"]),
        ]

    async def health(self) -> bool:
        if not self._api_key:
            return False
        try:
            llm = self.get_chat_model(model="gpt-4o-mini", temperature=0)
            await llm.ainvoke([{"role": "user", "content": "hi"}])
            return True
        except Exception:
            return False

    async def startup(self) -> None:
        if not self._api_key:
            logger.warning("OPENAI_API_KEY not set")
        else:
            logger.info("OpenAI backend ready (%s)", self._default_model)

    async def shutdown(self) -> None:
        pass


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    result = []
    for m in messages:
        if m.role == "system":
            result.append(SystemMessage(content=m.content))
        elif m.role == "assistant":
            result.append(AIMessage(content=m.content))
        else:
            result.append(HumanMessage(content=m.content))
    return result
```

```python [src/klaus/models/registry.py (add factory)]
from klaus.models.backends.openai import OpenAIBackend

BACKEND_FACTORIES: dict[str, type] = {
    "ollama": OllamaBackend,
    "gemini": GeminiBackend,
    "huggingface": HuggingFaceBackend,
    "openai": OpenAIBackend,  # ← add this
}
```

```yaml [config/klaus.yaml]
model_backends:
  openai:
    type: openai
    default_model: gpt-4o
    locality: cloud
    options:
      api_key: ${OPENAI_API_KEY}
```

:::

## Backend Interface

Backends use duck typing — no abstract base class. The registry expects these methods:

| Method | Required | Called by |
|--------|----------|----------|
| `get_chat_model(model, temperature, **kwargs)` | **Yes** | Agent via registry |
| `generate(request) → GenerateResponse` | **Yes** | REST API |
| `stream(request) → AsyncIterator[str]` | **Yes** | REST API |
| `list_models() → list[ModelInfo]` | **Yes** | Models page, model selector |
| `health() → bool` | **Yes** | Health checks, routing |
| `startup()` | Optional | Called on registration |
| `shutdown()` | Optional | Called on removal |
| `backend_type` (property) | Optional | Logging |

### Constructor Signature

The registry creates backends via `_create_backend(config)` which passes:

```python
kwargs = {"base_url": config.base_url}
if config.default_model:
    kwargs["default_model"] = config.default_model
if config.options:
    kwargs["options"] = config.options
```

::: warning
Your constructor **must** accept `base_url` and **should** accept `default_model` and `options`.
:::

## Adding Vision Support

If your backend supports image inputs, handle the `images` field on `ChatMessage`:

```python
def _to_lc_messages(messages: list[ChatMessage]) -> list:
    from langchain_core.messages import HumanMessage

    result = []
    for m in messages:
        if m.role == "user" and m.images:
            content = [{"type": "text", "text": m.content}]
            for img in m.images:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}"},
                })
            result.append(HumanMessage(content=content))
        else:
            # standard message conversion ...
    return result
```

## How It All Connects

```
config/klaus.yaml
  └─ model_backends.openai.type = "openai"
       │
       ▼
BACKEND_FACTORIES["openai"] = OpenAIBackend
       │
       ▼
ModelRegistry.register_from_config()
  └─ _create_backend(config) → OpenAIBackend(...)
       │
       ▼
TaskRouter.resolve(task="coding")
  └─ Decision(backend="openai", model="gpt-4o")
       │
       ▼
klausAgent._build_agent(backend="openai", model="gpt-4o")
  └─ registry.get_chat_model(backend="openai")
       └─ ChatOpenAI(model="gpt-4o")
```

## Configuration Reference

```yaml
model_backends:
  your_backend:
    type: openai            # Must match a key in BACKEND_FACTORIES
    base_url: https://...   # Optional, passed to constructor
    default_model: gpt-4o   # Optional, used when none specified
    locality: cloud         # "local" or "cloud" — affects routing
    models: []              # Optional list of model names
    options:                # Optional dict passed to constructor
      api_key: ${ENV_VAR}   # Supports env var interpolation
```

## Files to Touch

| File | What to change |
|------|----------------|
| `src/klaus/models/backends/your_backend.py` | Create your backend class |
| `src/klaus/models/registry.py` | Add to `BACKEND_FACTORIES` |
| `config/klaus.yaml` | Add config block |
| `.env.example` | Add API key env var |
| `pyproject.toml` | Add LangChain integration package |
| `tests/test_your_backend.py` | Add tests |
