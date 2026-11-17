"""Plan every story page as a scene with a beat and lines."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import Cache
    from .llm import LLMClient
    from .story import Story
    from .understand import BookContent

LINE_KINDS = ("narration", "dialogue")


@dataclass
class Line:
    """One spoken line of a page."""

    kind: str
    text: str
    speaker: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this line."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> Line:
        """Build a line from its external JSON shape."""
        raise NotImplementedError


@dataclass
class PageScene:
    """Beat, lines, duration and transition of one page."""

    index: int
    beat: str = ""
    lines: list[Line] = field(default_factory=list)
    duration: int = 6  # Seconds of video, estimated from the lines.
    transition: str = "cut"
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this scene."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> PageScene:
        """Build a scene from its external JSON shape."""
        raise NotImplementedError


@dataclass
class Screenplay:
    """Scenes of a whole book, one per page."""

    id: str = ""
    pages: list[PageScene] = field(default_factory=list)
    model: str = ""
    error: str = ""

    @property
    def page_count(self) -> int:
        raise NotImplementedError

    def to_dict(self) -> dict:
        """Return the external JSON shape of this screenplay."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> Screenplay:
        """Build a screenplay from its external JSON shape."""
        raise NotImplementedError


def build_screenplay(
    content: BookContent,
    story: Story,
    client: LLMClient,
    *,
    cache: Cache | None = None,
) -> Screenplay:
    """Write the beat and lines of every story page."""
    raise NotImplementedError


def save_screenplay(
    screenplay: Screenplay,
    root: str | Path | None = None,
) -> Path:
    """Write the screenplay to <root>/<id>/screenplay.json."""
    raise NotImplementedError
