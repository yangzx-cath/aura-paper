"""The published release of one book: the film, its subtitles and facts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .time import now_iso


@dataclass
class PublishCast:
    """One character a reader can put a name to."""

    id: str = ""
    name: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this character."""
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> PublishCast:
        """Build a character from its external JSON shape."""
        return cls(
            id=str(data.get("id") or "").strip(),
            name=str(data.get("name") or "").strip(),
        )


@dataclass
class BookPublish:
    """Everything the reader needs to play one book."""

    id: str = ""
    title: str = ""
    language: str = ""
    seconds: float = 0.0
    cues: int = 0
    film: str = ""
    vtt: str = ""
    cover: str = ""
    cast: list[PublishCast] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this release."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "title": self.title,
            "language": self.language,
            "seconds": self.seconds,
            "cues": self.cues,
            "film": self.film,
            "vtt": self.vtt,
            "cover": self.cover,
            "cast": [member.to_dict() for member in self.cast],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookPublish:
        """Build a release from its external JSON shape."""
        cast = data.get("cast")
        return cls(
            id=str(data.get("id") or "").strip(),
            title=str(data.get("title") or "").strip(),
            language=str(data.get("language") or "").strip(),
            seconds=_float_value(data.get("seconds")),
            cues=int(data.get("cues") or 0),
            film=str(data.get("film") or "").strip(),
            vtt=str(data.get("vtt") or "").strip(),
            cover=str(data.get("cover") or "").strip(),
            cast=(
                [
                    PublishCast.from_dict(item)
                    for item in cast
                    if isinstance(item, dict)
                ]
                if isinstance(cast, list)
                else []
            ),
            error=str(data.get("error") or "").strip(),
        )


# Read a number that may be missing or written as text.
def _float_value(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
