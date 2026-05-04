# Memory System

klaus uses a **hierarchical memory tree** backed by **PostgreSQL + pgvector** for persistent, searchable knowledge.

## Overview

```
/                              ← Root
├── /knowledge                 ← Agent's learned knowledge
│   ├── /skills                ← Hermes-style procedures
│   ├── /user                  ← User preferences/facts
│   └── /system                ← System-generated insights
├── /conversations             ← Per-session summaries
│   └── /session-id            ← Latest exchange snapshot
└── /superpowers               ← Registered capabilities
    ├── /mcp                   ← MCP bridge metadata
    ├── /memory                ← Memory tools description
    ├── /skills                ← Skills superpower metadata
    └── /image_generation      ← Image gen description
```

The tree lives in memory and is persisted as a single JSONB blob in PostgreSQL. Nodes under `/knowledge` and `/user` are additionally indexed as 384-dimensional vectors in pgvector for semantic search.

## Components

### MemoryNode

Each node can be both a branch (has children) **and** a leaf (has content):

```python
@dataclass
class MemoryNode:
    id: str                    # Short UUID (12 hex chars)
    name: str                  # Node name (path segment)
    content: str               # Stored text content
    metadata: dict             # Arbitrary key-value metadata
    tags: list[str]            # For filtering and search
    children: dict[str, Node]  # Child nodes by name
    created_at: float          # Unix timestamp
    updated_at: float          # Unix timestamp
    access_count: int          # How often accessed
```

### MemoryTree

Filesystem-like path operations:

| Method | Description |
|--------|-------------|
| `put(path, content, metadata, tags)` | Create/update node (creates intermediates like `mkdir -p`) |
| `get(path)` | Retrieve node by path |
| `delete(path)` | Remove node and subtree |
| `move(src, dst)` | Move subtree |
| `ls(path)` | List child names |
| `walk(path)` | DFS traversal |
| `search(query, root_path)` | Keyword search with TF-style scoring |
| `recent(root_path, n)` | Most recently updated nodes |
| `context_for(path, depth)` | Ancestors + siblings for context injection |

### MemoryManager

Owns the tree and handles persistence:

| Method | Description |
|--------|-------------|
| `startup()` | Load tree from PostgreSQL |
| `shutdown()` | Flush embeddings + save |
| `put(path, content)` | Write to tree, queue for embedding |
| `flush_embeddings()` | Index queued paths into pgvector |
| `maybe_save()` | Auto-save if dirty; always flushes embeddings |

::: tip
When `put()` is called with a path starting with `/knowledge` or `/user`, the content is automatically queued for vector embedding. Call `flush_embeddings()` to index immediately, or let `maybe_save()` handle it.
:::

### MemoryIndex

Combines keyword matching with semantic search:

| Method | Description |
|--------|-------------|
| `search()` | Keyword + tag + recency scoring |
| `semantic_search()` | pgvector cosine similarity |
| `hybrid_search()` | Blended keyword + semantic results |
| `gather_context()` | Build context string for agent injection |
| `index_node()` | Embed and store a single node |

### EmbeddingModel

- **Model:** `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensions:** 384
- **Size:** ~80MB, CPU-friendly
- **Loading:** Lazy — first `encode()` call loads the model

## Data Flow

### Writing knowledge

```
Agent calls remember("python/tips", "Use list comprehensions")
       │
       ▼
MemoryManager.put("/knowledge/python/tips", content)
       │
       ├── MemoryTree.put() — creates/updates node
       ├── mark_dirty() — flags for persistence
       └── Queue for embedding
       │
       ▼
flush_embeddings()
       │
       ├── EmbeddingModel.encode(content) → [384 floats]
       └── Database.save_embedding(path, content, vector)
```

### Reading knowledge

```
User: "How do I write Python efficiently?"
       │
       ▼
MemoryIndex.gather_context(query)
       │
       ├── Conversation context (recent exchange)
       ├── hybrid_search(query, root="/knowledge")
       │   ├── Keyword: "python", "efficiently" → scored
       │   └── Semantic: embed query → pgvector cosine search
       │       └── SELECT ... ORDER BY embedding <=> $1
       │   └── Merge: keyword × 0.4 + semantic × 6.0
       └── Superpowers capabilities list
       │
       ▼
Context injected into agent system prompt
```

## Hybrid Search Scoring

::: info Scoring formula
1. **Keyword** — Term frequency in content/name, tag matches, recency (`e^(-age/3600)`), access bonus
2. **Semantic** — pgvector cosine distance → `similarity = 1 - distance`
3. **Merge** — Both found: `keyword × 0.4 + semantic × 10 × 0.6`. Semantic-only: `similarity × 10`
:::

## PostgreSQL Schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE memory_tree (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    data     JSONB NOT NULL,
    saved_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE conversations (
    id         SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    model      TEXT,
    backend    TEXT,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE routing_rules (
    task       TEXT PRIMARY KEY,
    rule       JSONB NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE embeddings (
    id         SERIAL PRIMARY KEY,
    path       TEXT NOT NULL,
    content    TEXT NOT NULL,
    embedding  vector(384) NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
```

## Agent Tools

The agent accesses memory through these built-in tools:

| Tool | Description |
|------|-------------|
| `remember(path, content)` | Store at `/knowledge/{path}`, immediately flush to pgvector |
| `recall(path)` | Read from `/knowledge/{path}` |
| `search_memory(query)` | Hybrid search across the entire tree |
| `list_memory(path)` | List children at a path |

The **Skills** superpower stores versioned procedures at `/knowledge/skills/`.

## Self-Improvement

After complex interactions (3+ tool calls), the agent stores a reflection:

```python
self._memory.put(
    "/knowledge/system/last_complex_task",
    f"Complex task ({tool_call_count} tool calls): {summary}..."
    " → Consider creating a skill.",
)
```

This appears in memory context for future requests, encouraging skill creation.

## Knowledge Graph UI

The Knowledge page visualizes the memory tree as a force-directed graph:

- **Nodes** are circles, color-coded by branch
- **Edges** connect parent → child
- **Click** a node to see its full content
- **Data** from `GET /api/memory/graph`
