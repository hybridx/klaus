"""Langfuse tracing integration.

Langfuse provides observability for every LLM call, tool use, and agent step.
When LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY are set, tracing is
automatically enabled. Otherwise, it's silently disabled.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_langfuse_available: bool | None = None


def is_langfuse_configured() -> bool:
    """Return True if Langfuse credentials are in the environment."""
    return bool(os.environ.get("LANGFUSE_SECRET_KEY") and os.environ.get("LANGFUSE_PUBLIC_KEY"))


def get_langfuse_handler(metadata: dict[str, Any] | None = None):
    """Return a Langfuse callback handler for LangChain, or None if not configured."""
    global _langfuse_available

    if _langfuse_available is False:
        return None

    if not is_langfuse_configured():
        if _langfuse_available is None:
            logger.debug("Langfuse not configured — tracing disabled")
            _langfuse_available = False
        return None

    try:
        from langfuse.callback import CallbackHandler

        handler = CallbackHandler(
            session_id=metadata.get("session_id") if metadata else None,
            user_id=metadata.get("user_id") if metadata else None,
            metadata=metadata,
        )
        _langfuse_available = True
        return handler
    except Exception as exc:
        if _langfuse_available is None:
            logger.warning("Langfuse import failed — tracing disabled: %s", exc)
            _langfuse_available = False
        return None


def flush_langfuse() -> None:
    """Flush any pending Langfuse traces (call on shutdown)."""
    if not is_langfuse_configured():
        return
    try:
        from langfuse import Langfuse

        lf = Langfuse()
        lf.flush()
    except Exception:
        pass
