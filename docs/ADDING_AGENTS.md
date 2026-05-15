# Adding Model Backends

klaus supports multiple LLM providers through its **Model Registry**. Each provider is a backend class that wraps a LangChain chat model. This guide covers adding a new backend.

## Concepts

| Concept | What it means |
|---------|---------------|
| **Backend** | A class that wraps a specific LLM provider (Ollama, Gemini, HuggingFace, etc.) |
| **Registry** | `ModelRegistry` manages all backends, routes requests, and provides health checks |
| **Factory** | `BACKEND_FACTORIES` maps config type strings to backend classes |
| **Task Router** | Picks which backend + model to use based on task type and routing rules |

## Existing Backends

| Backend | Provider | Config type | Default model | Key feature |
|---------|----------|-------------|---------------|-------------|
| `OllamaBackend` | Ollama (local) | `ollama` | `llama3.2` | Local-first, vision support |
| `GeminiBackend` | Google AI | `gemini` | `gemini-2.5-flash` | Cloud API, API key auth |
| `HuggingFaceBackend` | HuggingFace Hub | `huggingface` | `Qwen/Qwen3-235B-A22B` | Inference API, vision support |

## Quick Start

### 1. Create the backend file

Create `src/klaus/models/backends/openai.py`:

```python
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

    def get_chat_model(
        self,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs,
    ):
        """Return a LangChain chat model for the agent to use."""
        return ChatOpenAI(
            model=model or self._default_model,
            temperature=temperature,
            api_key=self._api_key,
            base_url=self._base_url,
            **kwargs,
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Non-streaming completion."""
        llm = self.get_chat_model(
            model=request.model,
            temperature=request.temperature,
        )
        lc_messages = _to_lc_messages(request.messages)
        result = await llm.ainvoke(lc_messages)
        return GenerateResponse(
            content=result.content if isinstance(result.content, str) else str(result.content),
            model=request.model or self._default_model,
        )

    async def stream(self, request: GenerateRequest):
        """Streaming completion — yields text chunks."""
        llm = self.get_chat_model(
            model=request.model,
            temperature=request.temperature,
        )
        lc_messages = _to_lc_messages(request.messages)
        async for chunk in llm.astream(lc_messages):
            if chunk.content:
                yield chunk.content

    async def list_models(self) -> list[ModelInfo]:
        """Return available models."""
        return [
            ModelInfo(name="gpt-4o", backend="openai", capabilities=["chat", "vision"]),
            ModelInfo(name="gpt-4o-mini", backend="openai", capabilities=["chat"]),
        ]

    async def health(self) -> bool:
        """Check if the backend is reachable."""
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
            logger.warning("OpenAI API key not set — configure OPENAI_API_KEY")
        else:
            logger.info("OpenAI backend ready (model: %s)", self._default_model)

    async def shutdown(self) -> None:
        pass


def _to_lc_messages(messages: list[ChatMessage]) -> list:
    """Convert klaus ChatMessages to LangChain message objects."""
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

### 2. Register the factory

In `src/klaus/models/registry.py`, add the import and factory entry:

```python
from klaus.models.backends.openai import OpenAIBackend

BACKEND_FACTORIES: dict[str, type] = {
    "ollama": OllamaBackend,
    "gemini": GeminiBackend,
    "huggingface": HuggingFaceBackend,
    "openai": OpenAIBackend,  # ← add this
}
```

### 3. Add configuration

In `config/klaus.yaml`:

```yaml
model_backends:
  openai:
    type: openai
    default_model: gpt-4o
    locality: cloud
    options:
      api_key: ${OPENAI_API_KEY}
```

In `.env.example`:

```
OPENAI_API_KEY=sk-...
```

### 4. Add routing rules (optional)

```yaml
task_routing:
  creative:
    preferred_backend: openai
    preferred_model: gpt-4o
```

## Backend Interface

Backends use duck typing — there's no abstract base class. The registry and agent expect these methods:

| Method | Required | Called by |
|--------|----------|----------|
| `get_chat_model(model, temperature, **kwargs)` | **Yes** | Agent (via registry) to get a LangChain chat model |
| `generate(request: GenerateRequest) -> GenerateResponse` | **Yes** | REST API for non-streaming chat |
| `stream(request: GenerateRequest) -> AsyncIterator[str]` | **Yes** | REST API for streaming chat |
| `list_models() -> list[ModelInfo]` | **Yes** | Models page, model selector |
| `health() -> bool` | **Yes** | Health checks, routing decisions |
| `startup()` | Optional | Called on registration if present |
| `shutdown()` | Optional | Called on unregistration if present |
| `backend_type` (property) | Optional | Logging and identification |

### Constructor signature

The registry creates backends via `_create_backend(config)` which passes:

```python
kwargs = {"base_url": config.base_url}
if config.default_model:
    kwargs["default_model"] = config.default_model
if config.options:
    kwargs["options"] = config.options
```

Your constructor **must** accept `base_url` and **should** accept `default_model` and `options`.

## Adding Vision (Multimodal) Support

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
            # ... standard message conversion
```

The Ollama and HuggingFace backends both implement this pattern.

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
  └─ _create_backend(config) → OpenAIBackend(base_url=..., ...)
       │
       ▼
registry.register("openai", backend)
  └─ backend.startup() called
       │
       ▼
TaskRouter.resolve(task="coding")
  └─ Returns Decision(backend="openai", model="gpt-4o")
       │
       ▼
klausAgent._build_agent(backend="openai", model="gpt-4o")
  └─ registry.get_chat_model(backend="openai", model="gpt-4o")
       └─ OpenAIBackend.get_chat_model(model="gpt-4o")
            └─ Returns ChatOpenAI(model="gpt-4o")
```

## Configuration Reference

In `config/klaus.yaml`, each backend entry supports:

```yaml
model_backends:
  your_backend:
    type: openai          # Must match a key in BACKEND_FACTORIES
    base_url: https://... # Optional, passed to constructor
    default_model: gpt-4o # Optional, the model to use when none specified
    locality: cloud       # "local" or "cloud" — affects routing preference
    models: []            # Optional list of available model names
    options:              # Optional dict passed to constructor
      api_key: ${ENV_VAR} # Supports env var interpolation
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
| `README.md` | Update architecture diagram and config example |
| `CONTRIBUTING.md` | Mention the new backend |

## Testing

```python
import pytest
from klaus.models.backends.openai import OpenAIBackend


class TestOpenAIBackend:
    def test_backend_type(self):
        b = OpenAIBackend()
        assert b.backend_type == "openai"

    def test_default_model(self):
        b = OpenAIBackend()
        assert b._default_model == "gpt-4o"

    def test_get_chat_model_returns_langchain_model(self):
        b = OpenAIBackend(options={"api_key": "test-key"})
        model = b.get_chat_model()
        assert model is not None

    async def test_list_models(self):
        b = OpenAIBackend()
        models = await b.list_models()
        assert len(models) > 0

    async def test_health_no_key(self):
        b = OpenAIBackend()
        assert await b.health() is False
```
