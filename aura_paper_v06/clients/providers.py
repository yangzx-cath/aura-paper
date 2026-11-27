"""Choose the video generation client for the render stage."""

from __future__ import annotations

import os

from .minimax import MiniMaxClient
from .seedance import SeedanceClient
from .video import VideoClient

DEFAULT_PROVIDER = "seedance"


def make_video_client(provider: str | None = None) -> VideoClient:
    """Build the client named by provider or AURA_VIDEO_PROVIDER."""
    name = (
        provider or os.environ.get("AURA_VIDEO_PROVIDER") or DEFAULT_PROVIDER
    )
    name = name.strip().lower()
    if name == "seedance":
        return SeedanceClient.from_env()
    if name == "minimax":
        return MiniMaxClient.from_env()
    raise ValueError(f"unknown video provider: {name}")
