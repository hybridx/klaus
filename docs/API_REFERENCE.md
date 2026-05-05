# API Reference

klaus exposes a REST + SSE API via FastAPI. All routes are prefixed with `/api` except `/health` and `/` (dashboard).

## Health & Dashboard

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | System health: backend status, MCP count, agent readiness, memory size, superpowers |
| `GET` | `/` | Serves the built React dashboard (`ui/dist/index.html`) |
| `GET` | `/assets/*` | Static frontend assets |
| `GET` | `/api/images/*` | Generated images served from `data/images/` |

### `GET /health`

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "backends": { "ollama": true },
  "mcp_servers": 0,
  "agent_ready": true,
  "memory_nodes": 11,
  "superpowers": 4
}
```

---

## Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Non-streaming chat through the LangGraph agent |

### `POST /api/chat`

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "task": "chat",
    "temperature": 0.7
  }'
```

The primary chat interface uses **SSE** for streaming events and **REST** for sending messages (see below).

---

## Models

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/models` | List all models grouped by backend |
| `GET` | `/api/models/health` | Health status per backend |
| `GET` | `/api/models/backends` | List registered backend names |

### `GET /api/models`

```bash
curl http://localhost:8000/api/models
```

```json
{
  "ollama": [
    { "name": "llama3.2", "backend": "ollama", "size": "2.0GB", "capabilities": ["chat"] }
  ]
}
```

---

## Routing

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/routing/rules` | List all task routing rules |
| `POST` | `/api/routing/rules` | Create or update a routing rule |
| `DELETE` | `/api/routing/rules/{task}` | Delete a routing rule |
| `GET` | `/api/routing/resolve` | Preview routing decision for a task |
| `GET` | `/api/routing/backends` | Backends with locality, health, default model |
| `GET` | `/api/routing/status` | Router debug info and counters |

### `POST /api/routing/rules`

```bash
curl -X POST http://localhost:8000/api/routing/rules \
  -H "Content-Type: application/json" \
  -d '{
    "task": "coding",
    "rule": {
      "preferred_backend": "ollama",
      "preferred_model": "granite-code:8b",
      "fallback_backends": ["gemini"]
    }
  }'
```

### `GET /api/routing/resolve`

```bash
curl "http://localhost:8000/api/routing/resolve?task=coding"
```

```json
{
  "backend": "ollama",
  "model": "granite-code:8b",
  "task": "coding",
  "reason": "task rule match"
}
```

---

## Memory

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/memory/tree` | Full memory tree summary |
| `GET` | `/api/memory/ls?path=/` | List children at a path |
| `GET` | `/api/memory/get?path=/knowledge` | Get a specific node |
| `POST` | `/api/memory/put?path=/knowledge/foo` | Create or update a node (JSON body) |
| `DELETE` | `/api/memory/delete?path=/knowledge/foo` | Delete a node |
| `GET` | `/api/memory/search?q=python&max_results=10` | Search the memory tree |
| `GET` | `/api/memory/graph` | Flat node list for graph visualization |

### `GET /api/memory/graph`

Returns all nodes as a flat list optimized for rendering in React Flow:

```json
{
  "nodes": [
    {
      "id": "abc123",
      "label": "knowledge",
      "path": "/knowledge",
      "parent": "root-id",
      "content_preview": "",
      "tags": [],
      "branch": "knowledge",
      "children_count": 3,
      "access_count": 0
    }
  ]
}
```

---

## Conversations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/conversations/` | List recent sessions (with message counts) |
| `GET` | `/api/conversations/{session_id}` | Get messages for a session |
| `DELETE` | `/api/conversations/` | Delete all conversation history |

### `GET /api/conversations/`

```bash
curl http://localhost:8000/api/conversations/?limit=20
```

```json
{
  "sessions": [
    {
      "session_id": "abc-123",
      "message_count": 12,
      "last_active": 1777934356.69
    }
  ]
}
```

---

## MCP (Model Context Protocol)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/mcp/servers` | List MCP servers and status |
| `POST` | `/api/mcp/servers` | Register a new MCP server |
| `DELETE` | `/api/mcp/servers/{name}` | Unregister a server |
| `POST` | `/api/mcp/servers/{name}/connect` | Connect a registered server |
| `GET` | `/api/mcp/servers/{name}/tools` | List tools for a server |
| `POST` | `/api/mcp/servers/{name}/call` | Call a tool on a server |
| `GET` | `/api/mcp/tools` | List all tools across servers |

### `POST /api/mcp/servers`

```bash
curl -X POST http://localhost:8000/api/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "filesystem",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "connect": true
  }'
```

---

## Superpowers

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/superpowers` | List registered superpowers and their status |
| `GET` | `/api/superpowers/tools` | List all tools from active superpowers |

---

## Events

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/events/history?n=50` | Recent event history |
| `GET` | `/api/events/stream?session_id=xxx` | SSE event stream |
| `POST` | `/api/events/chat/send` | Send a chat message |
| `POST` | `/api/events/chat/{id}/plan-action` | Approve/reject/edit a plan |

---

## SSE + REST Protocol

### SSE Stream

**URL:** `GET /api/events/stream?session_id=xxx`

On connection, the server replays the last 50 events from history, then streams live events. A keepalive comment is sent every 30 seconds.

### Client → Server (REST)

**Send a chat message:**

```bash
curl -X POST /api/events/chat/send \
  -H 'Content-Type: application/json' \
  -d '{"id": "session-123", "messages": [{"role": "user", "content": "Hello"}]}'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Session/conversation ID |
| `messages` | array | Yes | `[{role, content}]` |
| `images` | string[] | No | Base64-encoded images |
| `model` | string | No | Override model selection |
| `backend` | string | No | Override backend selection |
| `temperature` | number | No | Default 0.7 |
| `retry` | boolean | No | Re-send after interrupted generation |

**Plan actions:**

```bash
curl -X POST /api/events/chat/session-123/plan-action \
  -H 'Content-Type: application/json' \
  -d '{"action": "approve"}'
```

### Server → Client (SSE)

**Per-session events (sent to the requesting session):**

| Event type | Data fields | Description |
|------------|-------------|-------------|
| `model.routed` | `backend`, `model`, `reason`, `chat_id` | Model selection result |
| `chat.token` | `token`, `chat_id` | Streaming response token |
| `mcp.tool_called` | `name`, `args`, `chat_id` | Agent invoked a tool |
| `tool.result` | `name`, `content`, `chat_id` | Tool returned output |
| `chat.done` | `chat_id` | Response stream complete |
| `chat.error` | `error`, `chat_id` | Error during generation |

**Broadcast events (sent to all connected sessions):**

| Event type | Description |
|------------|-------------|
| `chat.request` | A chat was requested |
| `chat.response` | A chat completed |
| `backend.registered` | New model backend added |
| `backend.health` | Backend health changed |
| `mcp.registered` | MCP server registered |
| `mcp.connected` | MCP server connected |
| `routing.rule_set` | Routing rule created/updated |
| `routing.rule_removed` | Routing rule deleted |

Each event is JSON with `type`, `data`, and `ts` (timestamp) fields.
