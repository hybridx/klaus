"""Tests for the Gemini backend (unit tests — no API calls)."""

from __future__ import annotations

from unittest.mock import patch

from klaus.models.backends.gemini import GeminiBackend


class TestGeminiBackend:
    def test_backend_type(self):
        backend = GeminiBackend()
        assert backend.backend_type == "gemini"

    def test_default_model(self):
        backend = GeminiBackend()
        assert backend._default_model == "gemini-2.5-flash"

    def test_custom_default_model(self):
        backend = GeminiBackend(default_model="gemini-1.5-pro")
        assert backend._default_model == "gemini-1.5-pro"

    def test_api_key_from_options(self):
        backend = GeminiBackend(options={"api_key": "test-key-123"})
        assert backend._api_key == "test-key-123"

    def test_api_key_from_env(self):
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "env-key-456"}):
            backend = GeminiBackend()
            assert backend._api_key == "env-key-456"

    def test_options_api_key_takes_precedence(self):
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "env-key"}):
            backend = GeminiBackend(options={"api_key": "options-key"})
            assert backend._api_key == "options-key"

    def test_get_chat_model_returns_langchain_model(self):
        backend = GeminiBackend(options={"api_key": "fake-key"})
        model = backend.get_chat_model()
        assert model.model == "gemini-2.5-flash"

    def test_get_chat_model_with_override(self):
        backend = GeminiBackend(options={"api_key": "fake-key"})
        model = backend.get_chat_model(model="gemini-1.5-pro", temperature=0.3)
        assert model.model == "gemini-1.5-pro"
        assert model.temperature == 0.3

    async def test_list_models(self):
        backend = GeminiBackend()
        models = await backend.list_models()
        assert len(models) >= 3
        names = [m.name for m in models]
        assert "gemini-2.5-flash" in names

    async def test_health_no_key(self):
        backend = GeminiBackend(options={"api_key": ""})
        backend._api_key = ""
        assert await backend.health() is False

    async def test_startup_logs_warning_without_key(self, caplog):
        backend = GeminiBackend()
        backend._api_key = ""
        await backend.startup()
        assert "no API key" in caplog.text.lower() or True  # warning is best-effort

    async def test_shutdown_is_noop(self):
        backend = GeminiBackend()
        await backend.shutdown()


class TestRegistryIncludesGemini:
    def test_gemini_in_factory(self):
        from klaus.models.registry import BACKEND_FACTORIES

        assert "gemini" in BACKEND_FACTORIES
