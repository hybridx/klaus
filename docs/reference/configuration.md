# Configuration

klaus reads configuration from `config/klaus.yaml` with environment variable overrides.

## Full Configuration Reference

```yaml
server:
  host: "0.0.0.0"          # Bind address
  port: 8000                # HTTP port

database:
  url: postgresql://klaus:klaus@localhost:5432/klaus
  pool_min: 2               # asyncpg minimum pool size
  pool_max: 10              # asyncpg maximum pool size

model_backends:
  ollama:
    type: ollama             # Backend type (ollama | gemini | huggingface | custom)
    base_url: http://localhost:11434
    default_model: llama3.2
    locality: local          # "local" or "cloud" — affects routing priority
    models:                  # Optional explicit model list
      - llama3.2
      - granite-code:8b

  gemini:
    type: gemini
    default_model: gemini-2.0-flash
    locality: cloud
    options:
      api_key: ${GOOGLE_API_KEY}

  huggingface:
    type: huggingface
    default_model: Qwen/Qwen3-235B-A22B
    locality: cloud
    options:
      token: ${HF_TOKEN}

task_routing:
  coding:
    preferred_backend: ollama
    preferred_model: granite-code:8b
  creative:
    preferred_backend: gemini
    preferred_model: gemini-2.0-flash
  analysis:
    preferred_backend: huggingface
    preferred_model: Qwen/Qwen3-235B-A22B
  chat:
    preferred_backend: ollama
    preferred_model: llama3.2

mcp_servers: []              # MCP servers to auto-register on startup

tracing:
  enabled: false             # Enable Langfuse tracing
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://klaus:klaus@localhost:5432/klaus` |
| `GOOGLE_API_KEY` | Google AI API key for Gemini backend | — |
| `HF_TOKEN` | HuggingFace Hub token | — |
| `OPENAI_API_KEY` | OpenAI API key (if using OpenAI backend) | — |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key (optional tracing) | — |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key (optional tracing) | — |

## Environment Variable Interpolation

In `klaus.yaml`, use `${ENV_VAR}` syntax to reference environment variables:

```yaml
options:
  api_key: ${GOOGLE_API_KEY}
```

This resolves at load time via `os.path.expandvars()`.

## Precedence

1. Environment variables (highest priority)
2. `config/klaus.yaml`
3. Built-in defaults (lowest priority)

## `.env` File

Place environment variables in `.env` at the project root. The dev server loads it automatically.

```bash
DATABASE_URL=postgresql://klaus:klaus@localhost:5432/klaus
GOOGLE_API_KEY=your-key-here
HF_TOKEN=hf_your-token-here
```

::: warning
Never commit `.env` to version control. The `.gitignore` already excludes it.
:::

## Model Backend Types

| Type | LangChain Integration | Package |
|------|----------------------|---------|
| `ollama` | `ChatOllama` | `langchain-ollama` |
| `gemini` | `ChatGoogleGenerativeAI` | `langchain-google-genai` |
| `huggingface` | `huggingface_hub.InferenceClient` | `huggingface-hub` |

To add your own, see [Adding Model Backends](/guide/adding-backends).
