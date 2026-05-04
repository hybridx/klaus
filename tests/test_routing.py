"""Tests for the task router — model selection logic."""

from __future__ import annotations

import pytest

from klaus.config.settings import TaskRoutingRule
from klaus.routing.router import BackendMeta, TaskRouter


@pytest.fixture()
def router() -> TaskRouter:
    r = TaskRouter(prefer_local=True)
    r.register_backend(BackendMeta(name="ollama", locality="local", default_model="llama3.2"))
    r.register_backend(BackendMeta(name="openai", locality="cloud", default_model="gpt-4"))
    return r


class TestTaskRouter:
    def test_explicit_override(self, router: TaskRouter):
        decision = router.resolve(requested_backend="openai", requested_model="gpt-4")
        assert decision.backend == "openai"
        assert decision.model == "gpt-4"
        assert decision.reason == "explicit user override"

    def test_local_first_auto_selection(self, router: TaskRouter):
        decision = router.resolve()
        assert decision.backend == "ollama"
        assert "local-first" in decision.reason

    def test_prefer_local_disabled(self):
        r = TaskRouter(prefer_local=False)
        r.register_backend(BackendMeta(name="cloud_a", locality="cloud"))
        r.register_backend(BackendMeta(name="local_b", locality="local"))
        decision = r.resolve()
        assert decision.backend == "cloud_a"
        assert decision.reason == "auto-selection"

    def test_task_rule_routing(self, router: TaskRouter):
        router.set_rule("coding", TaskRoutingRule(
            preferred_backend="ollama",
            preferred_model="codellama",
        ))
        decision = router.resolve(task="coding")
        assert decision.backend == "ollama"
        assert decision.model == "codellama"
        assert "task routing rule" in decision.reason

    def test_task_rule_fallback(self, router: TaskRouter):
        router.set_rule("coding", TaskRoutingRule(
            preferred_backend="dead_backend",
            fallback_backends=["openai"],
        ))
        decision = router.resolve(task="coding")
        assert decision.backend == "openai"
        assert decision.fallback_used is True

    def test_unhealthy_backend_skipped(self, router: TaskRouter):
        router.update_health("ollama", healthy=False)
        decision = router.resolve()
        assert decision.backend == "openai"

    def test_all_unhealthy_falls_back_to_first(self):
        r = TaskRouter(prefer_local=True)
        r.register_backend(BackendMeta(name="a", locality="local", healthy=False))
        r.register_backend(BackendMeta(name="b", locality="cloud", healthy=False))
        decision = r.resolve()
        assert decision.backend == "a"

    def test_no_backends_raises(self):
        r = TaskRouter()
        with pytest.raises(RuntimeError, match="No backends registered"):
            r.resolve()

    def test_remove_rule(self, router: TaskRouter):
        router.set_rule("chat", TaskRoutingRule(preferred_backend="openai"))
        router.remove_rule("chat")
        assert "chat" not in router.get_rules()

    def test_load_rules(self, router: TaskRouter):
        rules = {
            "chat": TaskRoutingRule(preferred_backend="ollama"),
            "coding": TaskRoutingRule(preferred_backend="openai"),
        }
        router.load_rules(rules)
        assert len(router.get_rules()) == 2

    def test_unregister_backend(self, router: TaskRouter):
        router.unregister_backend("openai")
        decision = router.resolve()
        assert decision.backend == "ollama"
