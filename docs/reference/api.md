# API Reference

All endpoints are served at `http://localhost:8000/api/`.

## Health

### `GET /health`

Returns `200` with a JSON status object.

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok" }
```

## Chat

### `POST /api/chat`

Send a message and receive a streaming or non-streaming response.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "messages": [
      { "role": "user", "content": "Hello, what can you do?" }
    ],
    "session_id": "abc-123",
    "task": "chat"
  }'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | `ChatMessage[]` | Yes | Conversation messages |
| `session_id` | `string` | No | Session ID for persistence |
| `task` | `string` | No | Task type for routing |

## Models

### `GET /api/models`

List all registered backends and their models.

```bash
curl http://localhost:8000/api/models
```

```json
{
  "backends": {
    "ollama": {
      "models": ["llama3.2", "granite-code:8b"],
      "healthy": true
    },
    "gemini": {
      "models": ["gemini-2.5-flash"],
      "healthy": true
    }
  }
}
```

### `GET /api/models/{backend}/health`

Check a single backend's health.

```bash
curl http://localhost:8000/api/models/ollama/health
```

## Routing

### `GET /api/routing/rules`

List all task routing rules.

```bash
curl http://localhost:8000/api/routing/rules
```

### `POST /api/routing/rules`

Create or update a routing rule.

```bash
curl -X POST http://localhost:8000/api/routing/rules \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "coding",
    "rule": {
      "preferred_backend": "ollama",
      "preferred_model": "granite-code:8b"
    }
  }'
```

### `DELETE /api/routing/rules/{task}`

Remove a routing rule.

```bash
curl -X DELETE http://localhost:8000/api/routing/rules/coding
```

## Memory

### `GET /api/memory/tree`

Retrieve the full memory tree.

```bash
curl http://localhost:8000/api/memory/tree
```

### `GET /api/memory/graph`

Get a graph representation for visualization.

```bash
curl http://localhost:8000/api/memory/graph
```

```json
{
  "nodes": [
    { "id": "root", "label": "/", "level": 0 },
    { "id": "abc123", "label": "knowledge", "level": 1 }
  ],
  "edges": [
    { "source": "root", "target": "abc123" }
  ]
}
```

### `GET /api/memory/search?q={query}`

Search the memory tree (hybrid search with vector embeddings).

```bash
curl "http://localhost:8000/api/memory/search?q=python%20tips"
```

## Conversations

### `GET /api/conversations`

List all conversation sessions.

```bash
curl http://localhost:8000/api/conversations
```

### `GET /api/conversations/{session_id}`

Get messages for a specific session.

```bash
curl http://localhost:8000/api/conversations/abc-123
```

### `DELETE /api/conversations`

Delete all conversations.

```bash
curl -X DELETE http://localhost:8000/api/conversations
```

## MCP

### `GET /api/mcp/servers`

List registered MCP servers and their tools.

```bash
curl http://localhost:8000/api/mcp/servers
```

### `POST /api/mcp/servers`

Register a new MCP server.

```bash
curl -X POST http://localhost:8000/api/mcp/servers \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "filesystem",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  }'
```

### `DELETE /api/mcp/servers/{name}`

Unregister an MCP server.

```bash
curl -X DELETE http://localhost:8000/api/mcp/servers/filesystem
```

## Superpowers

### `GET /api/superpowers`

List all registered superpowers and their tools.

```bash
curl http://localhost:8000/api/superpowers
```

```json
{
  "superpowers": [
    {
      "name": "memory",
      "description": "Memory access tools",
      "active": true,
      "tools": ["remember", "recall", "search_memory", "list_memory"]
    }
  ]
}
```

### `GET /api/superpowers/tools`

List all tools provided by active superpowers (includes MD-based tools).

```bash
curl http://localhost:8000/api/superpowers/tools
```

## Orchestration Events

When multi-agent orchestration is active, these SSE events are emitted:

| Event | Data | Description |
|-------|------|-------------|
| `plan.created` | `{ plan: PlanStep[], chat_id }` | Planner decomposed the request into tasks |
| `plan.step_start` | `{ index, description, task_type, backend, model, chat_id }` | Executor started a sub-task |
| `plan.step_done` | `{ index, result_preview, chat_id }` | Executor completed a sub-task |
| `plan.consolidated` | `{ chat_id }` | Consolidator merged all results |

### PlanStep Schema

```json
{
  "index": 0,
  "description": "Write a Python function for prime numbers",
  "task_type": "coding",
  "backend": "ollama",
  "model": "granite-code:8b",
  "depends_on": []
}
```

See [Orchestration Guide](/guide/orchestration) for full details.
