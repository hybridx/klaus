"""Model management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from klaus.api.deps import get_state

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models():
    """List all models across all registered backends."""
    state = get_state()
    all_models = await state.model_registry.list_all_models()
    return {
        backend: [
            {
                "name": m.name,
                "backend": m.backend,
                "size": m.size,
                "quantization": m.quantization,
                "context_length": m.context_length,
                "parameter_count": m.parameter_count,
                "family": m.family,
                "capabilities": m.capabilities,
            }
            for m in models
        ]
        for backend, models in all_models.items()
    }


@router.get("/health")
async def models_health():
    """Health check for all model backends."""
    state = get_state()
    return await state.model_registry.health_check()


@router.get("/backends")
async def list_backends():
    """List registered backend names."""
    state = get_state()
    return {"backends": state.model_registry.backend_names}
