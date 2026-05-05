"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from klaus.api.deps import get_state, init_state
from klaus.api.routes import chat, conversations, events, mcp, memory, models, routing, superpowers
from klaus.config import load_settings
from klaus.events.bus import EventType
from klaus.routing.router import BackendMeta


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("klaus")

    db_cfg = settings.database
    state = init_state(
        prefer_local=settings.prefer_local,
        database_url=db_cfg.url,
        pool_min=db_cfg.pool_min,
        pool_max=db_cfg.pool_max,
    )

    # ── Database ─────────────────────────────────────────────
    logger.info("Connecting to PostgreSQL...")
    await state.init_db()

    # ── Memory ───────────────────────────────────────────────
    logger.info("Loading memory tree...")
    await state.memory.startup()

    # ── Embedding model (local via Ollama) ────────────────────
    from klaus.memory.index import EmbeddingModel

    embed_cfg = settings.embedding
    EmbeddingModel.get(model=embed_cfg.model, base_url=embed_cfg.base_url)
    logger.info("Embedding model: %s (local via Ollama at %s)", embed_cfg.model, embed_cfg.base_url)

    # ── Model backends ───────────────────────────────────────
    logger.info("Initializing model backends (LangChain)...")
    await state.model_registry.register_from_config(
        settings.model_backends,
        default=settings.default_backend,
    )

    for name, cfg in settings.model_backends.items():
        state.task_router.register_backend(
            BackendMeta(
                name=name,
                locality=cfg.locality,
                default_model=cfg.default_model,
            )
        )
        state.event_bus.emit(
            EventType.BACKEND_REGISTERED,
            {"name": name, "type": cfg.type, "locality": cfg.locality},
        )

    logger.info("Discovering model capabilities...")
    await state.model_registry.refresh_capabilities()

    for bname, model_caps in state.model_registry._capabilities_cache.items():
        for mname, caps in model_caps.items():
            logger.info("  %-30s [%s] %s", mname, bname, ", ".join(caps))

    if settings.task_routing:
        state.task_router.load_rules(settings.task_routing)
        logger.info("Loaded %d task routing rules from config", len(settings.task_routing))

    # Load rules saved in the database (overrides config for same task)
    from klaus.config.settings import TaskRoutingRule

    db_rules = await state.db.load_routing_rules()
    if db_rules:
        parsed = {task: TaskRoutingRule(**data) for task, data in db_rules.items()}
        state.task_router.load_rules(parsed)
        logger.info("Loaded %d task routing rules from database", len(db_rules))

    # ── MCP servers ──────────────────────────────────────────
    # Explicit servers from klaus.yaml connect immediately.
    # Auto-discovered servers (from mcp.json files) are registered
    # but only connected on first use — avoids startup crashes from
    # external MCP servers (Cursor, Claude, etc.) that may not be available.
    from klaus.config.settings import load_mcp_json

    explicit_mcp: dict = dict(settings.mcp_servers)
    discovered_mcp: dict = {}

    for mcp_path in settings.mcp_config_files:
        loaded = load_mcp_json(mcp_path)
        for name, cfg in loaded.items():
            if name not in explicit_mcp and name not in discovered_mcp:
                discovered_mcp[name] = cfg
                logger.info("Loaded MCP server '%s' from %s", name, mcp_path)

    _auto_paths = [
        Path("mcp.json"),
        Path(".cursor/mcp.json"),
        Path.home() / ".cursor" / "mcp.json",
    ]
    for ap in _auto_paths:
        if ap.exists():
            loaded = load_mcp_json(ap)
            for name, cfg in loaded.items():
                if name not in explicit_mcp and name not in discovered_mcp:
                    discovered_mcp[name] = cfg
                    logger.info("Auto-discovered MCP server '%s' from %s", name, ap)

    async def _register_mcp(name: str, mcp_cfg, *, auto_connect: bool) -> None:
        if not mcp_cfg.enabled:
            return
        try:
            await state.mcp_manager.register(
                name=name,
                command=mcp_cfg.command,
                args=mcp_cfg.args,
                env=mcp_cfg.env,
                url=mcp_cfg.url,
                headers=mcp_cfg.headers or None,
                auto_connect=auto_connect,
            )
            state.event_bus.emit(EventType.MCP_REGISTERED, {"name": name})
        except BaseException as exc:
            logger.warning("Failed to register MCP server '%s': %s", name, exc)

    for name, mcp_cfg in explicit_mcp.items():
        await _register_mcp(name, mcp_cfg, auto_connect=True)

    for name, mcp_cfg in discovered_mcp.items():
        await _register_mcp(name, mcp_cfg, auto_connect=False)

    # ── MD-based Tools ────────────────────────────────────────
    from klaus.mcp.md_tools import load_md_tools

    md_tools_dir = getattr(settings, "orchestrator", None)
    md_dir = md_tools_dir.md_tools_dir if md_tools_dir else "data/tools"
    md_tools = load_md_tools(md_dir)
    if md_tools:
        logger.info("Loaded %d MD-based tools from %s", len(md_tools), md_dir)
    state.md_tools = md_tools  # type: ignore[attr-defined]

    # ── Superpowers ──────────────────────────────────────────
    registry = state.init_superpowers()

    from klaus.superpowers.builtin.mcp_bridge import MCPBridge
    from klaus.superpowers.builtin.memory_tools import MemoryTools
    from klaus.superpowers.builtin.skills import SkillsSuperpower

    await registry.register(MCPBridge(state.mcp_manager, md_tools=md_tools))
    await registry.register(MemoryTools(state.memory, db=state.db))
    await registry.register(SkillsSuperpower(state.memory))
    logger.info(
        "Superpowers ready: %d active", registry.active_count
    )

    # ── MD-based Agents ────────────────────────────────────────
    from klaus.agents.md_agents import load_md_agents

    agents_dir = "data/agents"
    md_agents = load_md_agents(agents_dir)
    if md_agents:
        logger.info("Loaded %d MD-based agents from %s", len(md_agents), agents_dir)
    state.md_agents = md_agents  # type: ignore[attr-defined]

    # ── Agent ────────────────────────────────────────────────
    orch_cfg = settings.orchestrator.model_dump() if hasattr(settings, "orchestrator") else None
    state.init_agent(orchestrator_config=orch_cfg, md_agents=md_agents)
    logger.info(
        "LangGraph agent initialized (orchestrator: %s)",
        "enabled" if orch_cfg else "disabled",
    )

    from klaus.agents.tracing import is_langfuse_configured

    if is_langfuse_configured():
        logger.info("Langfuse tracing enabled")
    else:
        logger.info(
            "Langfuse not configured — set LANGFUSE_SECRET_KEY"
            " and LANGFUSE_PUBLIC_KEY to enable"
        )

    logger.info(
        "klaus is ready. Dashboard at http://%s:%s/",
        settings.server.host, settings.server.port,
    )
    yield

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("Shutting down...")
    from klaus.agents.tracing import flush_langfuse

    flush_langfuse()
    if state.superpowers:
        await state.superpowers.shutdown_all()
    await state.memory.shutdown()
    await state.model_registry.shutdown_all()
    await state.mcp_manager.shutdown_all()
    await state.db.close()


_UI_DIST = Path(__file__).parent / "ui" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title="klaus",
        description=(
            "Multi-agent AI assistant with memory tree,"
            " superpowers, and LangGraph agent"
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(chat.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(mcp.router, prefix="/api")
    app.include_router(routing.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(superpowers.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        index = _UI_DIST / "index.html"
        if index.exists():
            return index.read_text()
        return (
            "<h1>UI not built</h1>"
            "<p>Run <code>cd ui &amp;&amp; npm install &amp;&amp; npm run build</code> first.</p>"
        )

    from fastapi.staticfiles import StaticFiles

    assets_dir = _UI_DIST / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=assets_dir), name="static")

    images_dir = Path("data/images")
    images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/api/images", StaticFiles(directory=images_dir), name="images")

    @app.get("/health")
    async def health():
        state = get_state()
        backends = await state.model_registry.health_check()
        sp_count = state.superpowers.active_count if state.superpowers else 0
        return {
            "status": "ok",
            "backends": backends,
            "mcp_servers": len(state.mcp_manager.list_servers()),
            "agent_ready": state.agent is not None,
            "memory_nodes": state.memory.tree.size,
            "superpowers": sp_count,
        }

    return app
