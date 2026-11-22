"""The scenes and shots one book's video is built from."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso

# The three sounds a shot can carry.
LINE_KINDS = ("旁白", "对白", "音效")

# How the video for a shot is made from its panel.
SHOT_MODES = ("首帧", "扩景")

# How a shot meets the shot after it.
SHOT_JOINS = ("硬切", "叠化")


@dataclass
class AudioLine:
    """One piece of sound a shot carries."""

    kind: str = ""
    text: str = ""
    cast: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this sound."""
        return {"kind": self.kind, "text": self.text, "cast": self.cast}

    @classmethod
    def from_dict(cls, data: dict) -> AudioLine:
        """Build a sound from its external JSON shape."""
        return cls(
            kind=_kind(data.get("kind")),
            text=_text(data.get("text")),
            cast=_text(data.get("cast")),
        )


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
class Shot:
    """One clip, made from one panel."""

    id: str = ""
    scene: str = ""
    page: str = ""
    panel: int = 0
    cast: list[str] = field(default_factory=list)
    mode: str = ""
    join: str = ""
    camera: str = ""
    beats: list[str] = field(default_factory=list)
    audio: list[AudioLine] = field(default_factory=list)
    continuity: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this shot."""
        return {
            "id": self.id,
            "scene": self.scene,
            "page": self.page,
            "panel": self.panel,
            "cast": self.cast,
            "mode": self.mode,
            "join": self.join,
            "camera": self.camera,
            "beats": self.beats,
            "audio": [line.to_dict() for line in self.audio],
            "continuity": self.continuity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Shot:
        """Build a shot from its external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            scene=_text(data.get("scene")),
            page=_text(data.get("page")),
            panel=_int_value(data.get("panel")),
            cast=_text_list(data.get("cast")),
            mode=_text(data.get("mode")),
            join=_text(data.get("join")),
            camera=_text(data.get("camera")),
            beats=_text_list(data.get("beats")),
            audio=_audio_list(data.get("audio")),
            continuity=_text(data.get("continuity")),
        )


@dataclass
class BookStoryboard:
    """The scenes and shots of one book."""

    id: str = ""
    style: str = ""
    scenes: list[Scene] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this storyboard."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "style": self.style,
            "scenes": [item.to_dict() for item in self.scenes],
            "shots": [item.to_dict() for item in self.shots],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookStoryboard:
        """Build a storyboard from its external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            style=_text(data.get("style")),
            scenes=_scene_list(data.get("scenes")),
            shots=_shot_list(data.get("shots")),
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


# Read an integer, falling back to zero when the value is unusable.
def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read a sound kind, leaving it empty when it is not one of the three.
def _kind(value: object) -> str:
    kind = _text(value)
    return kind if kind in LINE_KINDS else ""


# Read the sounds of a shot, keeping the ones that carry text.
def _audio_list(value: object) -> list[AudioLine]:
    if not isinstance(value, list):
        return []
    items = [
        AudioLine.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.text]


# Read the scene list, keeping entries that carry an id.
def _scene_list(value: object) -> list[Scene]:
    if not isinstance(value, list):
        return []
    items = [Scene.from_dict(item) for item in value if isinstance(item, dict)]
    return [item for item in items if item.id]


# Read the shot list, keeping entries that name a page.
def _shot_list(value: object) -> list[Shot]:
    if not isinstance(value, list):
        return []
    items = [Shot.from_dict(item) for item in value if isinstance(item, dict)]
    return [item for item in items if item.page]
