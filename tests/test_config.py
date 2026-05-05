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
    load_mcp_json,
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


class TestLoadMcpJson:
    def test_load_cursor_format(self, tmp_path):
        mcp_json = tmp_path / "mcp.json"
        mcp_json.write_text(
            '{"mcpServers": {"products": {"command": "npx", "args": ["@scarlet-mesh/mcp-products"]}}}'
        )
        result = load_mcp_json(mcp_json)
        assert "products" in result
        assert result["products"].command == "npx"
        assert result["products"].args == ["@scarlet-mesh/mcp-products"]

    def test_load_with_url(self, tmp_path):
        mcp_json = tmp_path / "mcp.json"
        mcp_json.write_text(
            '{"mcpServers": {"atlas": {"url": "https://mcp.atlassian.com/v1/mcp/authv2"}}}'
        )
        result = load_mcp_json(mcp_json)
        assert result["atlas"].url == "https://mcp.atlassian.com/v1/mcp/authv2"
        assert result["atlas"].command == ""

    def test_load_with_env(self, tmp_path):
        mcp_json = tmp_path / "mcp.json"
        mcp_json.write_text(
            '{"mcpServers": {"devtools": {"command": "npx", "args": [], "env": {"PORT": "9222"}}}}'
        )
        result = load_mcp_json(mcp_json)
        assert result["devtools"].env == {"PORT": "9222"}

    def test_load_nonexistent_returns_empty(self):
        result = load_mcp_json("/nonexistent/mcp.json")
        assert result == {}

    def test_load_empty_servers(self, tmp_path):
        mcp_json = tmp_path / "mcp.json"
        mcp_json.write_text('{"mcpServers": {}}')
        result = load_mcp_json(mcp_json)
        assert result == {}
