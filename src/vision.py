"""Access the vision model through an OpenAI-compatible endpoint."""

from __future__ import annotations

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
        raise NotImplementedError("VisionClient.__init__")

    @classmethod
    def from_env(cls) -> VisionClient:
        """Build a client from the VISION_* environment variables."""
        raise NotImplementedError("VisionClient.from_env")

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
