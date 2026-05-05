"""Tests for the task router — model selection, classification, and duplicate detection."""

from __future__ import annotations

import pytest

from klaus.config.settings import TaskRoutingRule
from klaus.routing.router import (
    BackendMeta,
    TaskRouter,
    check_keyword_overlap,
    classify_task,
)


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


class TestClassifyTask:
    def test_classify_coding(self):
        assert classify_task("write a python function") == "coding"

    def test_classify_creative(self):
        assert classify_task("write me a poem about the sea") == "creative"

    def test_classify_no_match(self):
        assert classify_task("zzz nothing here zzz") is None

    def test_classify_with_extra_keywords(self):
        extra = {"translation": ["translate", "language", "i18n"]}
        assert classify_task("translate this to French", extra) == "translation"

    def test_extra_keywords_merge_with_defaults(self):
        extra = {"coding": ["terraform", "provisioning"]}
        assert classify_task("apply terraform provisioning") is None
        assert classify_task("apply terraform provisioning", extra) == "coding"

    def test_extra_keywords_new_task_wins(self):
        extra = {"devops": ["terraform", "kubernetes", "deploy", "helm"]}
        result = classify_task("deploy with helm on kubernetes", extra)
        assert result == "devops"


class TestRouterClassify:
    def test_classify_uses_rule_keywords(self, router: TaskRouter):
        router.set_rule("translation", TaskRoutingRule(
            preferred_backend="ollama",
            keywords=["translate", "language", "localize"],
        ))
        assert router.classify("translate this to Spanish") == "translation"

    def test_classify_without_rules_uses_defaults(self, router: TaskRouter):
        assert router.classify("write a python function") == "coding"

    def test_classify_rule_keywords_extend_defaults(self, router: TaskRouter):
        router.set_rule("coding", TaskRoutingRule(
            preferred_backend="ollama",
            keywords=["terraform"],
        ))
        assert router.classify("terraform plan") == "coding"

    def test_get_keyword_map_includes_rules(self, router: TaskRouter):
        router.set_rule("translation", TaskRoutingRule(
            preferred_backend="ollama",
            keywords=["translate", "language"],
        ))
        kw_map = router.get_keyword_map()
        assert "translation" in kw_map
        assert "translate" in kw_map["translation"]
        assert "coding" in kw_map


class TestKeywordOverlap:
    def test_no_overlap(self):
        existing = {"coding": ["code", "python", "debug"]}
        result = check_keyword_overlap(existing, "translation", ["translate", "language"])
        assert result is None

    def test_high_overlap_detected(self):
        existing = {"coding": ["code", "python", "debug", "implement"]}
        result = check_keyword_overlap(
            existing, "programming", ["code", "python", "debug"]
        )
        assert result == "coding"

    def test_same_task_ignored(self):
        existing = {"coding": ["code", "python", "debug"]}
        result = check_keyword_overlap(existing, "coding", ["code", "python"])
        assert result is None

    def test_empty_keywords_no_conflict(self):
        existing = {"coding": ["code", "python"]}
        result = check_keyword_overlap(existing, "chat", [])
        assert result is None

    def test_case_insensitive(self):
        existing = {"coding": ["Code", "Python"]}
        result = check_keyword_overlap(existing, "dev", ["code", "python", "debug"])
        assert result == "coding"

    def test_below_threshold(self):
        existing = {"coding": ["code", "python", "debug", "implement", "refactor"]}
        result = check_keyword_overlap(
            existing, "scripting", ["code", "bash", "shell", "terminal", "cli"],
            threshold=0.5,
        )
        assert result is None


class TestRuleKeywordsAndDescription:
    def test_rule_stores_keywords(self):
        rule = TaskRoutingRule(
            preferred_backend="ollama",
            keywords=["translate", "language"],
            description="Translation tasks",
        )
        assert rule.keywords == ["translate", "language"]
        assert rule.description == "Translation tasks"

    def test_rule_defaults_empty(self):
        rule = TaskRoutingRule(preferred_backend="ollama")
        assert rule.keywords == []
        assert rule.description == ""

    def test_rule_roundtrip(self):
        rule = TaskRoutingRule(
            preferred_backend="ollama",
            preferred_model="llama3.2",
            keywords=["test", "verify"],
            description="Testing tasks",
        )
        data = rule.model_dump()
        restored = TaskRoutingRule(**data)
        assert restored.keywords == ["test", "verify"]
        assert restored.description == "Testing tasks"
        assert restored.preferred_model == "llama3.2"
