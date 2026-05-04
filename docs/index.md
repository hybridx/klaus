---
layout: home

hero:
  name: klaus
  text: Multi-Agent AI Platform
  tagline: Local-first model routing, persistent memory, and a plugin system that grows with you.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/hybridx/klaus

features:
  - icon: 🧠
    title: Persistent Memory
    details: Hierarchical memory tree backed by PostgreSQL + pgvector. Semantic search via 384-dim embeddings. The agent remembers across sessions.
  - icon: 🔀
    title: Local-First Routing
    details: Task router prefers local models and falls back to cloud. Route coding to CodeLlama, creative to GPT-4, analysis to Qwen — all automatic.
  - icon: 🔌
    title: Superpowers Plugin System
    details: Every capability is a Superpower — MCP bridges, memory tools, image generation, self-improving skills. Add your own in one file.
  - icon: 🤖
    title: LangGraph Agent
    details: ReAct agent rebuilt per-request with the latest tools and routed model. Full tool call visibility in the UI.
  - icon: 🎨
    title: React Dashboard
    details: Chat with markdown, knowledge graph visualization, pipeline flow view, model management, dark/light themes.
  - icon: 🔗
    title: MCP Native
    details: Dynamic Model Context Protocol integration. Register MCP servers at runtime, tools auto-bridge to the agent.
---

## Quick Start

```bash
# Clone and set up
git clone https://github.com/hybridx/klaus.git && cd klaus

# Start PostgreSQL (required)
bash scripts/start-postgres.sh

# Build the frontend
cd ui && npm install && npm run build && cd ..

# Start the dev server
uv run klaus-dev
```

Open [http://localhost:8000](http://localhost:8000) to see the dashboard.
