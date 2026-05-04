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
    """Maps a task category to preferred models, with local-first fallback."""

    preferred_backend: str | None = Field(
        default=None, description="Backend to use (None = auto-select local-first)"
    )
    preferred_model: str | None = Field(
        default=None, description="Specific model to use for this task"
    )
    fallback_backends: list[str] = Field(
        default_factory=list, description="Ordered fallback backends if preferred is unavailable"
    )
    max_tokens: int | None = Field(default=None)
    temperature: float | None = Field(default=None)


class MCPServerConfig(BaseModel):
    """Configuration for a pre-registered MCP server."""

    command: str = Field(description="Command to launch the MCP server")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = Field(default=True)


class DatabaseConfig(BaseModel):
    """PostgreSQL connection configuration."""

    url: str = Field(
        default="postgresql://klaus:klaus@localhost:5432/klaus",
        description="PostgreSQL connection URL (or set DATABASE_URL env var)",
    )
    pool_min: int = Field(default=2, description="Minimum pool connections")
    pool_max: int = Field(default=10, description="Maximum pool connections")


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
    model_backends: dict[str, ModelBackendConfig] = Field(
        default_factory=lambda: {
            "ollama": ModelBackendConfig(type="ollama"),
        },
    )
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    default_backend: str = Field(default="ollama")
    task_routing: dict[str, TaskRoutingRule] = Field(
        default_factory=dict,
        description="Task category -> routing rule. E.g. 'chat', 'coding', 'summarization'",
    )
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
