"""Tests for the configuration system."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from klaus.config.settings import (
    MCPServerConfig,
    ModelBackendConfig,
    Settings,
    TaskRoutingRule,
    load_settings,
)


class TestSettings:
    def test_default_settings(self):
        settings = Settings()
        assert settings.server.host == "0.0.0.0"
        assert settings.server.port == 8000
        assert settings.default_backend == "ollama"
        assert settings.prefer_local is True
        assert settings.log_level == "info"

    def test_default_backend_config(self):
        settings = Settings()
        assert "ollama" in settings.model_backends
        cfg = settings.model_backends["ollama"]
        assert cfg.type == "ollama"
        assert cfg.locality == "local"

    def test_task_routing_rule_defaults(self):
        rule = TaskRoutingRule()
        assert rule.preferred_backend is None
        assert rule.preferred_model is None
        assert rule.fallback_backends == []

    def test_mcp_server_config(self):
        cfg = MCPServerConfig(command="npx", args=["-y", "mcp-server"])
        assert cfg.command == "npx"
        assert cfg.enabled is True

    def test_model_backend_config_defaults(self):
        cfg = ModelBackendConfig(type="ollama")
        assert cfg.base_url == "http://localhost:11434"
        assert cfg.locality == "local"
        assert cfg.models == []


class TestLoadSettings:
    def test_load_from_yaml(self):
        config = {
            "server": {"host": "127.0.0.1", "port": 9000},
            "default_backend": "test",
            "log_level": "debug",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            path = f.name

        settings = load_settings(path)
        assert settings.server.host == "127.0.0.1"
        assert settings.server.port == 9000
        assert settings.log_level == "debug"

        Path(path).unlink()

    def test_load_nonexistent_returns_defaults(self):
        settings = load_settings("/nonexistent/path.yaml")
        assert settings.server.port == 8000

    def test_load_with_none_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        settings = load_settings(None)
        assert settings.server.port == 8000
