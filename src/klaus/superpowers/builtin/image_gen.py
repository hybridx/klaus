"""Image Generation superpower — lets the agent create images via HF Inference API.

Uses huggingface_hub.InferenceClient.text_to_image() with models like
FLUX.1-schnell. Generated images are saved locally and served via static mount.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from langchain_core.tools import StructuredTool

from klaus.superpowers.base import Superpower

logger = logging.getLogger(__name__)

_IMAGES_DIR = Path("data/images")


class ImageGeneration(Superpower):
    """Generate images from text prompts using HuggingFace models."""

    def __init__(self, default_model: str = "black-forest-labs/FLUX.1-schnell") -> None:
        super().__init__()
        self._default_model = default_model
        self._token = os.getenv("HF_TOKEN", "")

    @property
    def name(self) -> str:
        return "image_generation"

    @property
    def description(self) -> str:
        return "Generate images from text descriptions using HuggingFace models"

    @property
    def tags(self) -> list[str]:
        return ["image", "generation", "creative"]

    async def activate(self) -> None:
        await super().activate()
        _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        if not self._token:
            logger.warning("Image generation has no HF_TOKEN — set it in .env")

    def get_tools(self) -> list[StructuredTool]:
        token = self._token
        default_model = self._default_model

        async def generate_image(prompt: str, model: str = "") -> str:
            """Generate an image from a text prompt. Returns a markdown image link."""
            if not token:
                return "Error: HF_TOKEN not configured. Set it in .env to enable image generation."

            try:
                from huggingface_hub import InferenceClient
                client = InferenceClient(token=token)
                image = client.text_to_image(
                    prompt,
                    model=model or default_model,
                )

                filename = f"{uuid.uuid4().hex[:12]}.png"
                filepath = _IMAGES_DIR / filename
                image.save(str(filepath))

                return f"![Generated image]({'/api/images/' + filename})\n\n*Prompt: {prompt}*"
            except Exception as exc:
                logger.error("Image generation failed: %s", exc)
                return f"Error generating image: {exc}"

        return [
            StructuredTool.from_function(
                coroutine=generate_image,
                name="generate_image",
                description=(
                    "Generate an image from a text description. "
                    "Returns a markdown image link. Use descriptive, "
                    "detailed prompts for best results."
                ),
            ),
        ]
