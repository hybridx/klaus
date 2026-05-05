"""Task router — resolves which backend + model to use for a given task.

Supports:
- User-defined task→model mappings (config or runtime API)
- Local-first preference: local backends are tried before cloud
- Explicit overrides: user can force a specific backend/model per request
- Health-aware fallback: skips unhealthy backends
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from klaus.config.settings import TaskRoutingRule

logger = logging.getLogger(__name__)

_TASK_KEYWORDS: dict[str, list[str]] = {
    "coding": [
        "code", "function", "class", "bug", "debug", "refactor", "implement",
        "compile", "syntax", "algorithm", "python", "javascript", "typescript",
        "rust", "java", "html", "css", "sql", "api", "endpoint", "regex",
        "git", "docker", "deploy", "test", "unit test", "script", "import",
        "variable", "loop", "array", "list", "dict", "struct", "type",
        "error", "exception", "stack trace", "traceback", "program",
    ],
    "reasoning": [
        "think", "reason", "logic", "proof", "deduce", "infer", "conclude",
        "analyze", "evaluate", "compare", "contrast", "argue", "debate",
        "philosophy", "math", "equation", "solve", "puzzle", "riddle",
        "paradox", "hypothesis", "theorem",
    ],
    "creative": [
        "write", "story", "poem", "creative", "imagine", "fiction",
        "character", "dialogue", "narrative", "plot", "essay", "blog",
        "song", "lyrics", "screenplay", "brainstorm",
    ],
    "analysis": [
        "analyze", "data", "statistics", "chart", "graph", "trend",
        "insight", "report", "metric", "measure", "benchmark", "performance",
        "research", "study", "findings", "correlation",
    ],
    "summarization": [
        "summarize", "summary", "tldr", "brief", "condense", "recap",
        "overview", "digest", "key points", "highlights",
    ],
}


def classify_task(text: str) -> str | None:
    """Classify user text into a task type using keyword matching."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for task, keywords in _TASK_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[task] = score
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


@dataclass
class RoutingDecision:
    backend: str
    model: str | None
    task: str | None
    reason: str
    fallback_used: bool = False


@dataclass
class BackendMeta:
    name: str
    locality: str  # "local" | "cloud"
    healthy: bool = True
    default_model: str | None = None


class TaskRouter:
    """Resolves backend + model for each request based on task type and preferences."""

    def __init__(self, prefer_local: bool = True) -> None:
        self._prefer_local = prefer_local
        self._rules: dict[str, TaskRoutingRule] = {}
        self._backends: dict[str, BackendMeta] = {}

    def register_backend(self, meta: BackendMeta) -> None:
        self._backends[meta.name] = meta

    def unregister_backend(self, name: str) -> None:
        self._backends.pop(name, None)

    def set_rule(self, task: str, rule: TaskRoutingRule) -> None:
        self._rules[task] = rule
        logger.info("Task routing rule set: %s -> %s", task, rule)

    def remove_rule(self, task: str) -> None:
        self._rules.pop(task, None)

    def get_rules(self) -> dict[str, TaskRoutingRule]:
        return dict(self._rules)

    def load_rules(self, rules: dict[str, TaskRoutingRule]) -> None:
        self._rules.update(rules)

    def update_health(self, backend: str, healthy: bool) -> None:
        if backend in self._backends:
            self._backends[backend].healthy = healthy

    def resolve(
        self,
        task: str | None = None,
        requested_backend: str | None = None,
        requested_model: str | None = None,
    ) -> RoutingDecision:
        """Decide which backend + model to use.

        Priority order:
        1. Explicit user override (requested_backend/model)
        2. Task-specific routing rule
        3. Local-first auto-selection
        """
        if requested_backend:
            return RoutingDecision(
                backend=requested_backend,
                model=requested_model,
                task=task,
                reason="explicit user override",
            )

        if task and task in self._rules:
            rule = self._rules[task]
            backend = self._pick_from_rule(rule)
            if backend:
                return RoutingDecision(
                    backend=backend,
                    model=requested_model or rule.preferred_model,
                    task=task,
                    reason=f"task routing rule for '{task}'",
                    fallback_used=backend != rule.preferred_backend,
                )

        backend = self._auto_select()
        return RoutingDecision(
            backend=backend,
            model=requested_model,
            task=task,
            reason="local-first auto-selection" if self._prefer_local else "auto-selection",
        )

    def _pick_from_rule(self, rule: TaskRoutingRule) -> str | None:
        if rule.preferred_backend:
            meta = self._backends.get(rule.preferred_backend)
            if meta and meta.healthy:
                return rule.preferred_backend

        for fb in rule.fallback_backends:
            meta = self._backends.get(fb)
            if meta and meta.healthy:
                return fb

        return self._auto_select()

    def _auto_select(self) -> str:
        healthy = [m for m in self._backends.values() if m.healthy]
        if not healthy:
            all_names = list(self._backends.keys())
            if all_names:
                return all_names[0]
            raise RuntimeError("No backends registered")

        if self._prefer_local:
            local = [m for m in healthy if m.locality == "local"]
            if local:
                return local[0].name

        return healthy[0].name
