"""The scenes of one book: where and when each stretch happens."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso


@dataclass
class Scene:
    """One stretch of the story, in one place."""

    id: str = ""
    name: str = ""
    location: str = ""
    pages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this scene."""
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "pages": self.pages,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Scene:
        """Build a scene from its external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            name=_text(data.get("name")),
            location=_text(data.get("location")),
            pages=_text_list(data.get("pages")),
        )


@dataclass
class BookScenes:
    """The scenes of one book."""

    id: str = ""
    scenes: list[Scene] = field(default_factory=list)
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these scenes."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "scenes": [item.to_dict() for item in self.scenes],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookScenes:
        """Build the scenes from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            scenes=_scene_list(data.get("scenes")),
            model=_text(data.get("model")),
            error=_text(data.get("error")),
        )


# Read every text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read a list of text entries, dropping the empty ones.
def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    texts = (_text(item) for item in value)
    return [text for text in texts if text]


# Read the scene list, keeping entries that carry an id.
def _scene_list(value: object) -> list[Scene]:
    if not isinstance(value, list):
        return []
    items = [Scene.from_dict(item) for item in value if isinstance(item, dict)]
    return [item for item in items if item.id]
