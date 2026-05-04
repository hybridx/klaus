"""LangGraph agent — ReAct agent with memory, superpowers, and Langfuse tracing."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from klaus.agents.tools import collect_mcp_tools
from klaus.agents.tracing import get_langfuse_handler
from klaus.models.base import ChatMessage

if TYPE_CHECKING:
    from klaus.memory.store import MemoryManager
    from klaus.superpowers.registry import SuperpowerRegistry

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


class klausAgent:
    """A LangGraph-powered agent with memory tree and superpower tools.

    The agent is rebuilt per-request so it always has the latest tool set,
    the correct model, and fresh memory context injected as a system message.
    """

    def __init__(
        self,
        model_registry,
        mcp_manager,
        memory: MemoryManager | None = None,
        superpowers: SuperpowerRegistry | None = None,
    ) -> None:
        self._model_registry = model_registry
        self._mcp_manager = mcp_manager
        self._memory = memory
        self._superpowers = superpowers

    def _collect_tools(self) -> list:
        """Gather tools from superpowers first, fall back to raw MCP tools."""
        if self._superpowers:
            tools = self._superpowers.collect_tools()
            if tools:
                return tools

        return collect_mcp_tools(self._mcp_manager)

    def _build_memory_context(self, messages: list[ChatMessage]) -> str | None:
        """Extract relevant memory context for the current conversation."""
        if not self._memory:
            return None

        from klaus.memory.index import MemoryIndex

        index = MemoryIndex(self._memory.tree)

        user_text = " ".join(m.content for m in messages if m.role == "user")
        if not user_text:
            return None

        context = index.gather_context(user_text)
        return context if context.strip() else None

    def _build_agent(
        self,
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        memory_context: str | None = None,
    ):
        llm = self._model_registry.get_chat_model(
            backend=backend,
            model=model,
            temperature=temperature,
        )

        tools = self._collect_tools()

        prompt = None
        if memory_context:
            prompt = (
                "You are klaus, an AI assistant with persistent memory and extensible "
                "superpowers. Below is relevant context from your memory tree:\n\n"
                f"{memory_context}\n\n"
                "Use this context to give informed responses. You can use the 'remember' "
                "tool to store important facts and 'recall' or 'search_memory' to retrieve them."
            )

        if tools:
            logger.debug("Agent built with %d tools", len(tools))

        if prompt:
            return create_react_agent(llm, tools, prompt=prompt)
        return create_react_agent(llm, tools)

    async def invoke(
        self,
        messages: list[ChatMessage],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        memory_context = self._build_memory_context(messages)
        agent = self._build_agent(backend, model, temperature, memory_context)
        lc_messages = _to_lc_messages(messages)

        config: dict[str, Any] = {}
        langfuse_handler = get_langfuse_handler(metadata=metadata)
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        result = await agent.ainvoke(
            {"messages": lc_messages},
            config=config,
        )

        final_messages = result.get("messages", [])
        content = ""
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        # Store the interaction in conversation memory
        if self._memory:
            session_id = (metadata or {}).get("chat_id", "default")
            self._memory.put(
                f"/conversations/{session_id}/latest",
                content[:500],
                metadata={"model": model, "backend": backend},
                tags=["conversation"],
            )

        # Auto-save if needed
        if self._memory:
            await self._memory.maybe_save()

        return {
            "content": content,
            "messages": final_messages,
            "model": model,
        }

    async def stream(
        self,
        messages: list[ChatMessage],
        backend: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream agent execution — yields events for each step."""
        memory_context = self._build_memory_context(messages)
        agent = self._build_agent(backend, model, temperature, memory_context)
        lc_messages = _to_lc_messages(messages)

        config: dict[str, Any] = {"stream_mode": "messages"}
        langfuse_handler = get_langfuse_handler(metadata=metadata)
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        full_content = ""

        async for msg, _msg_metadata in agent.astream(
            {"messages": lc_messages},
            config=config,
            stream_mode="messages",
        ):
            if isinstance(msg, AIMessage):
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        yield {
                            "type": "tool_call",
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                        }
                elif msg.content:
                    token = msg.content if isinstance(msg.content, str) else str(msg.content)
                    full_content += token
                    yield {"type": "token", "content": token}

        # Store in conversation memory
        if self._memory and full_content:
            session_id = (metadata or {}).get("chat_id", "default")
            self._memory.put(
                f"/conversations/{session_id}/latest",
                full_content[:500],
                metadata={"model": model, "backend": backend, "streamed": True},
                tags=["conversation"],
            )
            await self._memory.maybe_save()

        yield {"type": "done"}
