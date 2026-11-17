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

from .utils import now_iso

LINE_KINDS = ("narration", "dialogue")

DEFAULT_DURATION = 6


@dataclass
class Line:
    """One spoken line of a page."""

    kind: str
    text: str
    speaker: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this line."""
        return {
            "kind": self.kind,
            "text": self.text,
            "speaker": self.speaker,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Line:
        """Build a line from its external JSON shape."""
        return cls(
            kind=_line_kind(data.get("kind")),
            text=str(data.get("text") or ""),
            speaker=str(data.get("speaker") or ""),
        )


@dataclass
class PageScene:
    """Beat, lines, duration and transition of one page."""

    index: int
    beat: str = ""
    lines: list[Line] = field(default_factory=list)
    duration: int = DEFAULT_DURATION  # Estimated from the lines.
    transition: str = "cut"
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this scene."""
        return {
            "index": self.index,
            "beat": self.beat,
            "lines": [line.to_dict() for line in self.lines],
            "duration": self.duration,
            "transition": self.transition,
            "model": self.model,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PageScene:
        """Build a scene from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            beat=str(data.get("beat") or ""),
            lines=_line_list(data.get("lines")),
            duration=int(data.get("duration") or DEFAULT_DURATION),
            transition=str(data.get("transition") or "cut"),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


@dataclass
class Screenplay:
    """Scenes of a whole book, one per page."""

    id: str = ""
    pages: list[PageScene] = field(default_factory=list)
    model: str = ""
    error: str = ""

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this screenplay."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "page_count": self.page_count,
            "pages": [page.to_dict() for page in self.pages],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Screenplay:
        """Build a screenplay from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            pages=_page_list(data.get("pages")),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


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


# Keep a line kind inside the supported set, defaulting to narration.
def _line_kind(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in LINE_KINDS else "narration"


# Read the line list, skipping entries that are not objects.
def _line_list(value: object) -> list[Line]:
    if not isinstance(value, list):
        return []
    return [Line.from_dict(item) for item in value if isinstance(item, dict)]


# Read the scene list, skipping entries that are not objects.
def _page_list(value: object) -> list[PageScene]:
    if not isinstance(value, list):
        return []
    return [
        PageScene.from_dict(item) for item in value if isinstance(item, dict)
    ]
