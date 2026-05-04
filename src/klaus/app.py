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
    for name, mcp_cfg in settings.mcp_servers.items():
        if mcp_cfg.enabled:
            try:
                await state.mcp_manager.register(
                    name=name,
                    command=mcp_cfg.command,
                    args=mcp_cfg.args,
                    env=mcp_cfg.env,
                )
                state.event_bus.emit(EventType.MCP_REGISTERED, {"name": name})
            except Exception as exc:
                logger.warning("Failed to register MCP server '%s': %s", name, exc)

    # ── Superpowers ──────────────────────────────────────────
    registry = state.init_superpowers()

    from klaus.superpowers.builtin.image_gen import ImageGeneration
    from klaus.superpowers.builtin.mcp_bridge import MCPBridge
    from klaus.superpowers.builtin.memory_tools import MemoryTools
    from klaus.superpowers.builtin.skills import SkillsSuperpower

    await registry.register(MCPBridge(state.mcp_manager))
    await registry.register(MemoryTools(state.memory, db=state.db))
    await registry.register(SkillsSuperpower(state.memory))
    await registry.register(ImageGeneration())
    logger.info(
        "Superpowers ready: %d active", registry.active_count
    )

    # ── Agent ────────────────────────────────────────────────
    state.init_agent()
    logger.info("LangGraph agent initialized")

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
