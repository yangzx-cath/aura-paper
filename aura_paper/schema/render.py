"""One generated video clip per shot, and how each run went."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso


@dataclass
class ShotRender:
    """One shot handed to the video model, and what came back."""

    shot: str = ""
    file: str = ""
    task_id: str = ""
    duration: int = 0
    resolution: str = ""
    seconds: float = 0.0
    cached: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this clip."""
        return {
            "shot": self.shot,
            "file": self.file,
            "task_id": self.task_id,
            "duration": self.duration,
            "resolution": self.resolution,
            "seconds": self.seconds,
            "cached": self.cached,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ShotRender:
        """Build a clip from its external JSON shape."""
        return cls(
            shot=_text(data.get("shot")),
            file=_text(data.get("file")),
            task_id=_text(data.get("task_id")),
            duration=_int_value(data.get("duration")),
            resolution=_text(data.get("resolution")),
            seconds=_float_value(data.get("seconds")),
            cached=bool(data.get("cached", False)),
            error=_text(data.get("error")),
        )


@dataclass
class BookRender:
    """Every clip of one book, in shot order."""

    id: str = ""
    model: str = ""
    shots: list[ShotRender] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these clips."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "shots": [shot.to_dict() for shot in self.shots],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookRender:
        """Build the clips from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            model=_text(data.get("model")),
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


# Read a duration in seconds, falling back to zero.
def _float_value(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


# Read the clip list, keeping the entries that name a shot.
def _shot_list(value: object) -> list[ShotRender]:
    if not isinstance(value, list):
        return []
    shots = [
        ShotRender.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [shot for shot in shots if shot.shot]
