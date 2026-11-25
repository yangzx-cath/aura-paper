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
class PublishPage:
    """One page of the film: when it plays and what it holds."""

    page: int = 0
    start: float = 0.0
    end: float = 0.0
    text: str = ""
    desc: str = ""
    cast: list[str] = field(default_factory=list)
    shots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        return {
            "page": self.page,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "desc": self.desc,
            "cast": self.cast,
            "shots": self.shots,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PublishPage:
        """Build a page from its external JSON shape."""
        cast = data.get("cast")
        shots = data.get("shots")
        return cls(
            page=int(data.get("page") or 0),
            start=_float_value(data.get("start")),
            end=_float_value(data.get("end")),
            text=str(data.get("text") or "").strip(),
            desc=str(data.get("desc") or "").strip(),
            cast=(
                [str(name) for name in cast if name]
                if isinstance(cast, list)
                else []
            ),
            shots=(
                [str(name) for name in shots if name]
                if isinstance(shots, list)
                else []
            ),
        )


@dataclass
class PublishShot:
    """One shot of the film: when it plays and which pages it shows."""

    id: str = ""
    scene: str = ""
    scene_name: str = ""
    start: float = 0.0
    end: float = 0.0
    pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this shot."""
        return {
            "id": self.id,
            "scene": self.scene,
            "scene_name": self.scene_name,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "pages": self.pages,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PublishShot:
        """Build a shot from its external JSON shape."""
        pages = data.get("pages")
        return cls(
            id=str(data.get("id") or "").strip(),
            scene=str(data.get("scene") or "").strip(),
            scene_name=str(data.get("scene_name") or "").strip(),
            start=_float_value(data.get("start")),
            end=_float_value(data.get("end")),
            pages=(
                [int(page) for page in pages if isinstance(page, int)]
                if isinstance(pages, list)
                else []
            ),
        )


@dataclass
class PublishTopic:
    """One thing a child can tap and hear about."""

    id: str = ""
    name: str = ""
    kind: str = ""
    aliases: list[str] = field(default_factory=list)
    visual: str = ""
    intro: str = ""
    pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this topic."""
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "aliases": self.aliases,
            "visual": self.visual,
            "intro": self.intro,
            "pages": self.pages,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PublishTopic:
        """Build a topic from its external JSON shape."""
        aliases = data.get("aliases")
        pages = data.get("pages")
        return cls(
            id=str(data.get("id") or "").strip(),
            name=str(data.get("name") or "").strip(),
            kind=str(data.get("kind") or "").strip(),
            aliases=(
                [str(word) for word in aliases if word]
                if isinstance(aliases, list)
                else []
            ),
            visual=str(data.get("visual") or "").strip(),
            intro=str(data.get("intro") or "").strip(),
            pages=(
                [int(page) for page in pages if isinstance(page, int)]
                if isinstance(pages, list)
                else []
            ),
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
    pages: list[PublishPage] = field(default_factory=list)
    shots: list[PublishShot] = field(default_factory=list)
    topics: list[PublishTopic] = field(default_factory=list)
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
            "pages": [page.to_dict() for page in self.pages],
            "shots": [shot.to_dict() for shot in self.shots],
            "topics": [topic.to_dict() for topic in self.topics],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookPublish:
        """Build a release from its external JSON shape."""
        cast = data.get("cast")
        pages = data.get("pages")
        shots = data.get("shots")
        topics = data.get("topics")
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
            pages=(
                [
                    PublishPage.from_dict(item)
                    for item in pages
                    if isinstance(item, dict)
                ]
                if isinstance(pages, list)
                else []
            ),
            shots=(
                [
                    PublishShot.from_dict(item)
                    for item in shots
                    if isinstance(item, dict)
                ]
                if isinstance(shots, list)
                else []
            ),
            topics=(
                [
                    PublishTopic.from_dict(item)
                    for item in topics
                    if isinstance(item, dict)
                ]
                if isinstance(topics, list)
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
