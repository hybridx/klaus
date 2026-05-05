"""klaus entrypoint — production and dev server."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _ensure_ollama_models(
    models: list[str],
    base_url: str = "http://localhost:11434",
) -> None:
    """Check Ollama for required models and pull any that are missing."""
    import httpx

    print("  [models] Checking required Ollama models...")
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        installed = {m["name"] for m in resp.json().get("models", [])}
    except Exception as exc:
        print(f"  [models] Ollama not reachable ({exc}) — skipping auto-pull")
        return

    for model in models:
        variants = [model]
        if ":" not in model:
            variants.append(f"{model}:latest")
        if any(v in installed for v in variants):
            print(f"  [models] ✓ {model}")
            continue

        print(f"  [models] Pulling {model} (this may take a while)...")
        try:
            resp = httpx.post(
                f"{base_url}/api/pull",
                json={"name": model, "stream": False},
                timeout=None,
            )
            if resp.status_code == 200:
                print(f"  [models] ✓ {model} pulled successfully")
            else:
                print(
                    f"  [models] ✗ Failed to pull {model}: "
                    f"{resp.status_code}",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(
                f"  [models] ✗ Failed to pull {model}: {exc}",
                file=sys.stderr,
            )


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

    ollama_url = "http://localhost:11434"
    for cfg in settings.model_backends.values():
        if cfg.type == "ollama":
            ollama_url = cfg.base_url
            break
    _ensure_ollama_models(settings.required_models, base_url=ollama_url)

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
