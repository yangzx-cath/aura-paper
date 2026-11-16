"""Generate one video clip per page and collect them into a book video."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import Cache
    from .minimax import MiniMaxClient
    from .story import Story
    from .understand import BookContent, PageContent


@dataclass
class VideoClip:
    """One generated video clip for a page."""

    index: int
    filename: str
    prompt: str
    task_id: str = ""
    model: str = ""
    duration: int = 6
    resolution: str = "768P"
    path: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this clip."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> VideoClip:
        """Build a clip from its external JSON shape."""
        raise NotImplementedError


@dataclass
class BookVideo:
    """All generated clips of one book."""

    id: str
    title: str
    source: str
    model: str = ""
    clips: list[VideoClip] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book video."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> BookVideo:
        """Build a book video from its external JSON shape."""
        raise NotImplementedError


def clip_path(
    book_id: str,
    index: int,
    root: str | Path | None = None,
) -> Path:
    """Return <root>/<book_id>/clips/page_01.mp4."""
    raise NotImplementedError


def generate_clip(
    content: BookContent,
    page: PageContent,
    story: Story,
    client: MiniMaxClient,
    *,
    root: str | Path | None = None,
    duration: int = 6,
    resolution: str = "768P",
) -> VideoClip:
    """Generate one page clip and return its metadata."""
    raise NotImplementedError


def build_video(
    content: BookContent,
    story: Story,
    client: MiniMaxClient,
    *,
    cache: Cache | None = None,
    root: str | Path | None = None,
    workers: int = 1,
) -> BookVideo:
    """Generate every page clip and return the book video."""
    raise NotImplementedError


def save_video(
    video: BookVideo,
    root: str | Path | None = None,
) -> Path:
    """Write the book video to <root>/<id>/video.json."""
    raise NotImplementedError
