"""klaus entrypoint — production and dev server."""

from __future__ import annotations


def cli() -> None:
    """Production entrypoint: `klaus`."""
    import uvicorn

    from klaus.config import load_settings

    settings = load_settings()
    uvicorn.run(
        "klaus.app:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        log_level=settings.log_level,
    )


def dev() -> None:
    """Dev entrypoint: `klaus-dev` or `make dev`.

    Auto-reload on file changes, debug logging.
    """
    import uvicorn

    from klaus.config import load_settings

    settings = load_settings()
    print("\n  klaus dev server — http://localhost:8000/\n")
    uvicorn.run(
        "klaus.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=settings.server.port,
        reload=True,
        reload_dirs=["src"],
        log_level="debug",
    )


if __name__ == "__main__":
    cli()
