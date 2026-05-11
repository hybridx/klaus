"""Configuration system — Pydantic models validated from YAML + env vars.

Loads secrets from .env (via python-dotenv), config from YAML, and allows
overrides via klaus_-prefixed environment variables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

load_dotenv()


class ModelBackendConfig(BaseModel):
    """Configuration for a single model backend (e.g. Ollama, HuggingFace)."""

    type: str = Field(description="Backend type identifier, e.g. 'ollama', 'huggingface', 'openai'")
    base_url: str = Field(default="http://localhost:11434", description="Base URL for the backend")
    models: list[str] = Field(default_factory=list, description="Pre-registered model names")
    default_model: str | None = Field(default=None, description="Default model for this backend")
    locality: str = Field(default="local", description="'local' or 'cloud'")
    options: dict[str, Any] = Field(default_factory=dict, description="Backend-specific options")


class TaskRoutingRule(BaseModel):
    """Maps a task category (intent) to preferred models, with keywords for classification."""

    preferred_backend: str | None = Field(
        default=None, description="Backend to use (None = auto-select local-first)"
    )
    preferred_model: str | None = Field(
        default=None, description="Specific model to use for this task"
    )
    fallback_backends: list[str] = Field(
        default_factory=list, description="Ordered fallback backends if preferred is unavailable"
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that trigger this intent during classification",
    )
    description: str = Field(
        default="", description="Human-readable description of this intent"
    )
    max_tokens: int | None = Field(default=None)
    temperature: float | None = Field(default=None)


class MCPServerConfig(BaseModel):
    """Configuration for a pre-registered MCP server.

    OAuth is handled automatically by the MCP SDK at the protocol level
    (metadata discovery, dynamic client registration, PKCE).  No manual
    auth config is needed — just provide the URL and click Connect.
    """

    command: str = Field(default="", description="Command to launch the MCP server")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    url: str | None = Field(
        default=None,
        description="SSE/HTTP transport URL (alternative to command)",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers for SSE/HTTP transport (e.g. Authorization)",
    )


def load_mcp_json(path: str | Path) -> dict[str, MCPServerConfig]:
    """Load MCP servers from a Cursor/Claude-style mcp.json file.

    Supports the standard format with optional auth:
        {
          "mcpServers": {
            "name": { "command": "...", "args": [...] },
            "atlas": {
              "url": "https://...",
              "auth": { "type": "oauth2", "authorize_url": "...", ... }
            }
          }
        }
    """
    import json

    p = Path(path)
    if not p.exists():
        return {}

    data = json.loads(p.read_text())
    servers_raw = data.get("mcpServers", {})
    result: dict[str, MCPServerConfig] = {}

    for name, cfg in servers_raw.items():
        if not isinstance(cfg, dict):
            continue

        command = cfg.get("command", "")
        args = cfg.get("args", [])

        # Handle commands with args baked in, e.g. "npx chrome-devtools-mcp@latest"
        if command and " " in command and not args:
            parts = command.split()
            command = parts[0]
            args = parts[1:]

        result[name] = MCPServerConfig(
            command=command,
            args=args,
            env=cfg.get("env", {}),
            enabled=True,
            url=cfg.get("url"),
            headers=cfg.get("headers", {}),
        )
    return result


class DatabaseConfig(BaseModel):
    """PostgreSQL connection configuration."""

    url: str = Field(
        default="postgresql://klaus:klaus@localhost:5432/klaus",
        description="PostgreSQL connection URL (or set DATABASE_URL env var)",
    )
    pool_min: int = Field(default=2, description="Minimum pool connections")
    pool_max: int = Field(default=10, description="Maximum pool connections")


class OrchestratorConfig(BaseModel):
    """Multi-agent orchestrator configuration."""

    planner_backend: str | None = Field(
        default=None, description="Backend for the planner model (None = use default)"
    )
    planner_model: str | None = Field(
        default=None, description="Model for planning/decomposition (None = backend default)"
    )
    md_tools_dir: str = Field(
        default="data/tools", description="Directory for MD-based tool definitions"
    )


class EmbeddingConfig(BaseModel):
    """Embedding model configuration — fully local by default via Ollama."""

    model: str = Field(default="nomic-embed-text", description="Ollama embedding model name")
    base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama base URL for embeddings",
    )


class ServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    reload: bool = Field(default=False)


class Settings(BaseSettings):
    """Root application settings.

    Loads from YAML config file, overridable by environment variables
    prefixed with klaus_.
    """

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    model_backends: dict[str, ModelBackendConfig] = Field(
        default_factory=lambda: {
            "ollama": ModelBackendConfig(type="ollama"),
        },
    )
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    mcp_config_files: list[str] = Field(
        default_factory=list,
        description="Paths to mcp.json files (Cursor/Claude format) to auto-load",
    )
    required_models: list[str] = Field(
        default_factory=lambda: ["llama3.2", "nomic-embed-text", "gemma4:latest"],
        description="Ollama models to auto-pull on dev startup if missing",
    )
    default_backend: str = Field(default="ollama")
    task_routing: dict[str, TaskRoutingRule] = Field(
        default_factory=dict,
        description="Task category -> routing rule. E.g. 'chat', 'coding', 'summarization'",
    )
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    prefer_local: bool = Field(
        default=True,
        description="When no explicit routing, prefer local backends over cloud",
    )
    langfuse_secret_key: str | None = Field(
        default=None, description="Langfuse secret key (or set LANGFUSE_SECRET_KEY env)"
    )
    langfuse_public_key: str | None = Field(
        default=None, description="Langfuse public key (or set LANGFUSE_PUBLIC_KEY env)"
    )
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse host URL",
    )
    log_level: str = Field(default="info")

    model_config = {
        "env_prefix": "klaus_",
        "env_nested_delimiter": "__",
    }


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from a YAML file, falling back to defaults."""
    if config_path is None:
        candidates = [Path("klaus.yaml"), Path("klaus.yml"), Path("config/klaus.yaml")]
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break

    if config_path is not None:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return Settings(**data)

    return Settings()
