"""One video generation job per shot."""

from __future__ import annotations

from dataclasses import dataclass, field

from .shot import ShotPanel
from .time import now_iso


@dataclass
class JobImage:
    """One image handed to the video model, and what it shows."""

    file: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this image."""
        return {"file": self.file, "note": self.note}

    @classmethod
    def from_dict(cls, data: dict) -> JobImage:
        """Build an image from its external JSON shape."""
        return cls(
            file=_text(data.get("file")),
            note=_text(data.get("note")),
        )


@dataclass
class JobLine:
    """One piece of sound placed on the timeline of a shot."""

    index: int = 0
    kind: str = ""
    cast: str = ""
    text: str = ""
    file: str = ""
    start_ms: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict:
        """Return the external JSON shape of this sound."""
        return {
            "index": self.index,
            "kind": self.kind,
            "cast": self.cast,
            "text": self.text,
            "file": self.file,
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> JobLine:
        """Build a sound from its external JSON shape."""
        return cls(
            index=_int_value(data.get("index")),
            kind=_text(data.get("kind")),
            cast=_text(data.get("cast")),
            text=_text(data.get("text")),
            file=_text(data.get("file")),
            start_ms=_int_value(data.get("start_ms")),
            duration_ms=_int_value(data.get("duration_ms")),
        )


@dataclass
class Job:
    """One shot, ready to hand to the video model."""

    shot: str = ""
    scene: str = ""
    location: str = ""
    join: str = ""
    prompt: str = ""
    images: list[JobImage] = field(default_factory=list)
    lines: list[JobLine] = field(default_factory=list)
    panels: list[ShotPanel] = field(default_factory=list)
    duration: int = 0
    audio_ms: int = 0
    ratio: str = ""
    resolution: str = ""
    audio: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this job."""
        return {
            "shot": self.shot,
            "scene": self.scene,
            "location": self.location,
            "join": self.join,
            "prompt": self.prompt,
            "images": [image.to_dict() for image in self.images],
            "lines": [line.to_dict() for line in self.lines],
            "panels": [panel.to_dict() for panel in self.panels],
            "duration": self.duration,
            "audio_ms": self.audio_ms,
            "ratio": self.ratio,
            "resolution": self.resolution,
            "audio": self.audio,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        """Build a job from its external JSON shape."""
        return cls(
            shot=_text(data.get("shot")),
            scene=_text(data.get("scene")),
            location=_text(data.get("location")),
            join=_text(data.get("join")),
            prompt=_text(data.get("prompt")),
            images=_image_list(data.get("images")),
            lines=_line_list(data.get("lines")),
            panels=_panel_list(data.get("panels")),
            duration=_int_value(data.get("duration")),
            audio_ms=_int_value(data.get("audio_ms")),
            ratio=_text(data.get("ratio")),
            resolution=_text(data.get("resolution")),
            audio=bool(data.get("audio", True)),
            error=_text(data.get("error")),
        )


@dataclass
class BookJobs:
    """Every shot of one book as a video generation job."""

    id: str = ""
    ratio: str = ""
    resolution: str = ""
    shots: list[Job] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these jobs."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "ratio": self.ratio,
            "resolution": self.resolution,
            "shots": [shot.to_dict() for shot in self.shots],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookJobs:
        """Build the jobs from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            ratio=_text(data.get("ratio")),
            resolution=_text(data.get("resolution")),
            shots=_shot_list(data.get("shots")),
            error=_text(data.get("error")),
        )


# Read a text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read an integer, falling back to zero when the value is unusable.
def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read the images of one job, keeping the entries that name a file.
def _image_list(value: object) -> list[JobImage]:
    if not isinstance(value, list):
        return []
    images = [
        JobImage.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [image for image in images if image.file]


# Read the sounds of one job, keeping the entries that name a kind.
def _line_list(value: object) -> list[JobLine]:
    if not isinstance(value, list):
        return []
    lines = [
        JobLine.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [line for line in lines if line.kind]


# Read the panels of one job, keeping the entries that name a page.
def _panel_list(value: object) -> list[ShotPanel]:
    if not isinstance(value, list):
        return []
    panels = [
        ShotPanel.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [panel for panel in panels if panel.page]


# Read the shot list, keeping the entries that name a shot.
def _shot_list(value: object) -> list[Job]:
    if not isinstance(value, list):
        return []
    shots = [Job.from_dict(item) for item in value if isinstance(item, dict)]
    return [shot for shot in shots if shot.shot]
