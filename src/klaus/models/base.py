"""Model abstractions — thin wrappers for data passing.

The actual LLM calls are now handled by LangChain chat models under the hood.
These dataclasses remain as the klaus-internal API contract so that routes
and the agent layer don't couple directly to LangChain types.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    images: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class GenerateRequest:
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = False
    tools: list[dict] | None = None
    options: dict = field(default_factory=dict)


@dataclass
class GenerateResponse:
    content: str
    model: str
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None
    usage: dict | None = None


@dataclass
class ModelInfo:
    name: str
    backend: str
    size: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    capabilities: list[str] = field(default_factory=list)
