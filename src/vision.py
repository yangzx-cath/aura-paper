"""Access the vision model through an OpenAI-compatible endpoint."""

from __future__ import annotations

import os
from pathlib import Path

# Environment variables:
#   VISION_BASE_URL, VISION_API_KEY, VISION_MODEL, VISION_TIMEOUT


class VisionError(Exception):
    """Raised when the endpoint cannot return a usable answer."""


class VisionClient:
    """Client for one OpenAI-compatible vision endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout: float

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def __repr__(self) -> str:
        return (
            f"VisionClient(base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout={self.timeout})"
        )

    @classmethod
    def from_env(cls) -> VisionClient:
        """Build a client from the VISION_* environment variables."""
        return cls(
            base_url=os.environ.get("VISION_BASE_URL", ""),
            api_key=os.environ.get("VISION_API_KEY", ""),
            model=os.environ.get("VISION_MODEL", ""),
            timeout=float(os.environ.get("VISION_TIMEOUT", "120")),
        )

    def analyze(
        self,
        prompt: str,
        image_path: Path,
        *,
        json_mode: bool = True,
    ) -> str:
        """Send one image with a prompt and return the reply text."""
        raise NotImplementedError("VisionClient.analyze")


def extract_json(text: str) -> dict:
    """Return the first JSON object found in text."""
    raise NotImplementedError("extract_json")
