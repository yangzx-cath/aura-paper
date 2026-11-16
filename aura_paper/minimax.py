"""Call the MiniMax video generation API (v2)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://api.minimax.io"
DEFAULT_MODEL = "MiniMax-H3"

# Status values returned by the query endpoint.
TASK_PENDING = ("queued", "running")
TASK_DONE = ("succeeded", "failed", "cancelled")


class MiniMaxError(Exception):
    """Raised when the service cannot return a usable result."""


@dataclass
class VideoRequest:
    """One video generation request."""

    prompt: str
    first_frame: Path | None = None
    last_frame: Path | None = None
    reference_images: list[Path] = field(default_factory=list)
    duration: int = 6
    resolution: str = "768P"
    ratio: str | None = None

    # Frames travel as data URLs; frame and reference inputs cannot
    # be mixed, and a text prompt is always required.
    def to_payload(self, model: str) -> dict:
        """Return the request body for the video generation endpoint."""
        raise NotImplementedError


@dataclass
class VideoTask:
    """Snapshot of one asynchronous video task."""

    task_id: str
    status: str = ""
    video_url: str = ""
    resolution: str = ""
    duration: int = 0
    error: str = ""

    @property
    def pending(self) -> bool:
        return self.status in TASK_PENDING

    @property
    def done(self) -> bool:
        return self.status in TASK_DONE

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"

    @classmethod
    def from_response(cls, data: dict) -> VideoTask:
        """Build a task from a create or query response body."""
        raise NotImplementedError


class MiniMaxClient:
    """Client for one MiniMax video generation endpoint."""

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
        max_wait: float = 600.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_wait = max_wait

    def __repr__(self) -> str:
        return (
            f"MiniMaxClient(base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout={self.timeout})"
        )

    @classmethod
    def from_env(cls) -> MiniMaxClient:
        """Build a client from the MINIMAX_* environment variables."""
        return cls(
            base_url=os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE_URL),
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            model=os.environ.get("MINIMAX_VIDEO_MODEL", DEFAULT_MODEL),
            timeout=float(os.environ.get("MINIMAX_TIMEOUT", "60")),
            poll_interval=float(os.environ.get("MINIMAX_POLL_INTERVAL", "5")),
            max_wait=float(os.environ.get("MINIMAX_MAX_WAIT", "600")),
        )

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        if not self.api_key:
            return ["MINIMAX_API_KEY"]
        return []

    # POST /v2/video_generation
    def create_task(self, request: VideoRequest) -> VideoTask:
        """Submit one generation task and return its first snapshot."""
        raise NotImplementedError

    # GET /v2/query/video_generation/{task_id}
    def get_task(self, task_id: str) -> VideoTask:
        """Return the current snapshot of one task."""
        raise NotImplementedError

    def wait_task(self, task_id: str) -> VideoTask:
        """Poll a task until it finishes or max_wait elapses."""
        raise NotImplementedError

    # The URL is time-limited, so download right away.
    def download(self, url: str, path: str | Path) -> Path:
        """Fetch a finished video to path and return the path."""
        raise NotImplementedError

    def generate(
        self,
        request: VideoRequest,
        path: str | Path,
    ) -> VideoTask:
        """Create, wait and download a video in one call."""
        raise NotImplementedError

    # Send one JSON POST and return the parsed body.
    def _post(self, path: str, payload: dict) -> dict:
        raise NotImplementedError

    # Send one GET and return the parsed body.
    def _get(self, path: str, params: dict) -> dict:
        raise NotImplementedError

    # Raise MiniMaxError on an error reply or a failed task.
    def _check(self, data: dict) -> dict:
        raise NotImplementedError
