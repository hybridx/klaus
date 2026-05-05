"""klaus entrypoint — production and dev server."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _build_ui() -> None:
    """Install deps and build the React UI into src/klaus/ui/dist/."""
    ui_dir = Path(__file__).resolve().parent.parent.parent / "ui"
    if not ui_dir.exists():
        print("  [ui] ui/ directory not found, skipping build")
        return

    node_modules = ui_dir / "node_modules"
    if not node_modules.exists():
        print("  [ui] Installing npm dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=ui_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  [ui] npm install failed:\n{result.stderr}", file=sys.stderr)
            return

    print("  [ui] Building UI...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=ui_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  [ui] Build failed:\n{result.stderr}", file=sys.stderr)
        return

    print("  [ui] Build complete → src/klaus/ui/dist/")


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

    Builds the UI, then starts the backend with auto-reload.
    """
    import uvicorn

    from klaus.config import load_settings

    settings = load_settings()

    print("\n  klaus dev server\n")
    _build_ui()
    print(f"\n  → http://localhost:{settings.server.port}/\n")

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
