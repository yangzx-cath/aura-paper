"""Interface for the Seedance video generation API.

The client submits one video task, polls it until it finishes, and
downloads the resulting clip. The HTTP implementation is not written yet.
"""

from __future__ import annotations

from pathlib import Path

from .video_types import (
    VideoError,
    VideoRequest,
    VideoTask,
)

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedance-2-0-fast-260128"


class SeedanceError(VideoError):
    """Error for Seedance calls."""


class SeedanceClient:
    """Client interface for one Seedance video generation endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout: float
    poll_interval: float
    max_wait: float

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        poll_interval: float = 5.0,
        max_wait: float = 1200.0,
    ) -> None:
        raise NotImplementedError("seedance client is not implemented yet")

    @classmethod
    def from_env(cls) -> SeedanceClient:
        """Build a client from ARK_API_KEY and the SEEDANCE_* variables."""
        raise NotImplementedError("seedance client is not implemented yet")

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        raise NotImplementedError("seedance client is not implemented yet")

    def create_task(self, request: VideoRequest) -> VideoTask:
        """Submit one generation task and return its first snapshot."""
        raise NotImplementedError("seedance client is not implemented yet")

    def get_task(self, task_id: str) -> VideoTask:
        """Return the current snapshot of one task."""
        raise NotImplementedError("seedance client is not implemented yet")

    def wait_task(self, task_id: str) -> VideoTask:
        """Poll a task until it finishes or max_wait elapses."""
        raise NotImplementedError("seedance client is not implemented yet")

    def download(self, url: str, path: str | Path) -> Path:
        """Fetch a finished video to path and return the path."""
        raise NotImplementedError("seedance client is not implemented yet")

    def generate(
        self,
        request: VideoRequest,
        path: str | Path,
    ) -> VideoTask:
        """Create, wait and download a video in one call."""
        raise NotImplementedError("seedance client is not implemented yet")
