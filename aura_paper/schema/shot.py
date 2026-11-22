"""The shots of one book: what each clip covers and how it sounds."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso

# The three sounds a shot can carry.
LINE_KINDS = ("旁白", "对白", "音效")

# How a shot meets the shot before it.
SHOT_JOINS = ("硬切", "叠化")


@dataclass
class ShotPanel:
    """One panel a shot is made from."""

    page: str = ""
    panel: int = 0

    def to_dict(self) -> dict:
        """Return the external JSON shape of this panel."""
        return {"page": self.page, "panel": self.panel}

    @classmethod
    def from_dict(cls, data: dict) -> ShotPanel:
        """Build a panel from its external JSON shape."""
        return cls(
            page=_text(data.get("page")),
            panel=_int_value(data.get("panel")),
        )


@dataclass
class AudioLine:
    """One piece of sound a shot carries."""

    kind: str = ""
    text: str = ""
    spoken: str = ""
    cast: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this sound."""
        return {
            "kind": self.kind,
            "text": self.text,
            "spoken": self.spoken,
            "cast": self.cast,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AudioLine:
        """Build a sound from its external JSON shape."""
        return cls(
            kind=_kind(data.get("kind")),
            text=_text(data.get("text")),
            spoken=_text(data.get("spoken")),
            cast=_text(data.get("cast")),
        )


@dataclass
class Shot:
    """One clip, made from the panels that show one action."""

    id: str = ""
    scene: str = ""
    panels: list[ShotPanel] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
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
            "panels": [item.to_dict() for item in self.panels],
            "cast": self.cast,
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
            panels=_shot_panel_list(data.get("panels")),
            cast=_text_list(data.get("cast")),
            join=_text(data.get("join")),
            camera=_text(data.get("camera")),
            beats=_text_list(data.get("beats")),
            audio=_audio_list(data.get("audio")),
            continuity=_text(data.get("continuity")),
        )


@dataclass
class BookShots:
    """The shots of one book, with the art style they are drawn in."""

    id: str = ""
    style: str = ""
    shots: list[Shot] = field(default_factory=list)
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these shots."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "style": self.style,
            "shots": [item.to_dict() for item in self.shots],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookShots:
        """Build the shots from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            style=_text(data.get("style")),
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


# Read the shot list, keeping entries that carry at least one panel.
def _shot_list(value: object) -> list[Shot]:
    if not isinstance(value, list):
        return []
    items = [Shot.from_dict(item) for item in value if isinstance(item, dict)]
    return [item for item in items if item.panels]


# Read the panels of one shot, keeping the ones that name a page.
def _shot_panel_list(value: object) -> list[ShotPanel]:
    if not isinstance(value, list):
        return []
    items = [
        ShotPanel.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.page]
