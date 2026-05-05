"""Task splitter — decomposes multi-part user messages into independent sub-tasks.

Detects conjunctions, numbered lists, and separators to split a single user
message into parts that can each be routed to a different model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from klaus.routing.router import classify_task


@dataclass
class SubTask:
    index: int
    text: str
    task_type: str | None


_ACTION_VERBS = (
    r"(?:create|write|make|build|generate|tell|show|describe|explain|find|"
    r"analyze|summarize|translate|draw|code|implement|debug|fix|run|"
    r"give|list|compare|check|do|send|open|search|identify)"
)

_CONJUNCTION_PATTERN = re.compile(
    r"""
    (?:                            # non-capturing group
      \.\s+(?:then|also|next)\s    # period then conjunction: "...code. Then write..."
    | ,\s*(?:then|and\s+also)\s    # comma then conjunction: "...code, then write..."
    | \s+then\s+                   # bare "then" surrounded by spaces
    | \s+and\s+also\s+             # "and also"
    | \s+after\s+that[,]?\s+       # "after that"
    | \s*;\s+                      # semicolons
    | \s+and\s+(?="""
    + _ACTION_VERBS
    + r""")                        # "and" + action verb: "...code and write..."
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_NUMBERED_ITEM = re.compile(
    r"^\s*(?:\d+[.)]\s+|[-*]\s+)",
    re.MULTILINE,
)


def split_tasks(text: str) -> list[SubTask]:
    """Split user text into independent sub-tasks.

    Returns a list of SubTask objects. Single-task messages return a list
    of one element (no behavior change for the caller).
    """
    text = text.strip()
    if not text:
        return [SubTask(index=0, text=text, task_type=None)]

    parts = _try_numbered_split(text)
    if parts is None:
        parts = _try_conjunction_split(text)

    if parts is None or len(parts) < 2:
        task_type = classify_task(text)
        return [SubTask(index=0, text=text, task_type=task_type)]

    results: list[SubTask] = []
    for i, part in enumerate(parts):
        cleaned = part.strip()
        if not cleaned:
            continue
        task_type = classify_task(cleaned)
        results.append(SubTask(index=i, text=cleaned, task_type=task_type))

    if len(results) < 2:
        task_type = classify_task(text)
        return [SubTask(index=0, text=text, task_type=task_type)]

    return results


def _try_numbered_split(text: str) -> list[str] | None:
    """Split on numbered list items (1. / 1) / - / *)."""
    matches = list(_NUMBERED_ITEM.finditer(text))
    if len(matches) < 2:
        return None

    parts: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        part = text[start:end].strip()
        if part:
            parts.append(part)

    return parts if len(parts) >= 2 else None


def _try_conjunction_split(text: str) -> list[str] | None:
    """Split on conjunctions like 'then', 'and also', semicolons."""
    parts = _CONJUNCTION_PATTERN.split(text)
    meaningful = [p.strip() for p in parts if p and p.strip() and len(p.strip()) > 5]
    return meaningful if len(meaningful) >= 2 else None
