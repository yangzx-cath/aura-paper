"""Provider-neutral video generation types.

These structures describe one asynchronous video request and task.
The clips stage consumes them to produce one VideoClip per page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .utils import IMAGE_SUFFIXES

# Status values returned by the supported providers.
TASK_PENDING = ("queued", "running")
TASK_DONE = ("succeeded", "failed", "cancelled", "expired")

DEFAULT_DURATION = 6


class VideoError(Exception):
    """Error for video generation calls."""


@dataclass
class VideoRequest:
    """One video generation request."""

    prompt: str
    first_frame: Path | None = None
    last_frame: Path | None = None
    reference_images: list[Path] = field(default_factory=list)
    duration: int = DEFAULT_DURATION
    resolution: str | None = None
    ratio: str | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        if not 4 <= self.duration <= 15:
            raise ValueError("duration must be 4 to 15 seconds")
        if self.reference_images and (self.first_frame or self.last_frame):
            raise ValueError("frames and reference images cannot be mixed")
        if self.last_frame is not None and self.first_frame is None:
            raise ValueError("last_frame needs first_frame")
        images = [self.first_frame, self.last_frame]
        images += self.reference_images
        for path in images:
            if path is None:
                continue
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                raise ValueError(f"unsupported image type: {path.suffix}")


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


class VideoClient(Protocol):
    """The methods the clips stage needs from a provider client."""

    model: str

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        ...

    def create_task(self, request: VideoRequest) -> VideoTask:
        """Submit one generation task."""
        ...

    def get_task(self, task_id: str) -> VideoTask:
        """Return the current snapshot of one task."""
        ...

    def wait_task(self, task_id: str) -> VideoTask:
        """Poll a task until it finishes or max_wait elapses."""
        ...

    def download(self, url: str, path: str | Path) -> Path:
        """Fetch a finished video to path and return the path."""
        ...

    def generate(
        self,
        request: VideoRequest,
        path: str | Path,
    ) -> VideoTask:
        """Create, wait and download a video in one call."""
        ...
