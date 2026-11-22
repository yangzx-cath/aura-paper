"""The characters of one book and the crops that stand for them."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso


@dataclass
class FigurePick:
    """One crop that may stand for a character."""

    page: str = ""
    figure: int = 0
    file: str = ""
    facing: str = ""
    area: float = 0.0


@dataclass
class Cast:
    """One character and the crops that show it best."""

    id: str = ""
    name: str = ""
    look: str = ""
    pictures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this character."""
        return {
            "id": self.id,
            "name": self.name,
            "look": self.look,
            "pictures": self.pictures,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Cast:
        """Build a character from its external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            name=_text(data.get("name")),
            look=_text(data.get("look")),
            pictures=_text_list(data.get("pictures")),
        )


@dataclass
class FigureCast:
    """One candidate crop, and the character it shows."""

    file: str = ""
    cast: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this crop."""
        return {"file": self.file, "cast": self.cast}

    @classmethod
    def from_dict(cls, data: dict) -> FigureCast:
        """Build a crop from its external JSON shape."""
        return cls(
            file=_text(data.get("file")),
            cast=_text(data.get("cast")),
        )


@dataclass
class Resolution:
    """One identity question the book answered, or could not answer."""

    page: int = 0
    issue: str = ""
    answer: str = ""
    evidence: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this resolution."""
        return {
            "page": self.page,
            "issue": self.issue,
            "answer": self.answer,
            "evidence": self.evidence,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Resolution:
        """Build a resolution from its external JSON shape."""
        return cls(
            page=_int_value(data.get("page")),
            issue=_text(data.get("issue")),
            answer=_text(data.get("answer")),
            evidence=_text(data.get("evidence")),
            reason=_text(data.get("reason")),
        )


@dataclass
class BookCast:
    """The characters of one book, and what was settled about them."""

    id: str = ""
    cast: list[Cast] = field(default_factory=list)
    figure_cast: list[FigureCast] = field(default_factory=list)
    resolved: list[Resolution] = field(default_factory=list)
    open: list[Resolution] = field(default_factory=list)
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this cast."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "cast": [member.to_dict() for member in self.cast],
            "figure_cast": [item.to_dict() for item in self.figure_cast],
            "resolved": [item.to_dict() for item in self.resolved],
            "open": [item.to_dict() for item in self.open],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookCast:
        """Build a cast from its external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            cast=_cast_list(data.get("cast")),
            figure_cast=_figure_cast_list(data.get("figure_cast")),
            resolved=_resolution_list(data.get("resolved")),
            open=_resolution_list(data.get("open")),
            model=_text(data.get("model")),
            error=_text(data.get("error")),
        )

    @property
    def unpictured(self) -> list[Cast]:
        """Return the characters no crop can stand for."""
        return [member for member in self.cast if not member.pictures]


# Read every text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read a list of text entries, dropping the empty ones.
def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    texts = (_text(item) for item in value)
    return [text for text in texts if text]


# Read an integer, falling back to zero when the value is unusable.
def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read the cast list, keeping entries that carry an id.
def _cast_list(value: object) -> list[Cast]:
    if not isinstance(value, list):
        return []
    members = [
        Cast.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [member for member in members if member.id]


# Read the crop list, keeping entries that name a file.
def _figure_cast_list(value: object) -> list[FigureCast]:
    if not isinstance(value, list):
        return []
    items = [
        FigureCast.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.file]


# Read a resolution list, keeping one entry per issue.
def _resolution_list(value: object) -> list[Resolution]:
    if not isinstance(value, list):
        return []
    items = [
        Resolution.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.issue]
