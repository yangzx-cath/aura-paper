"""One mixed take per shot: the clip with its sound track laid under it."""

from __future__ import annotations

from dataclasses import dataclass, field

from .time import now_iso


@dataclass
class ComposedShot:
    """One clip with the spoken lines placed on its timeline."""

    shot: str = ""
    file: str = ""
    audio: str = ""
    source: str = ""
    seconds: float = 0.0
    sound: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this take."""
        return {
            "shot": self.shot,
            "file": self.file,
            "audio": self.audio,
            "source": self.source,
            "seconds": self.seconds,
            "sound": self.sound,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ComposedShot:
        """Build a take from its external JSON shape."""
        return cls(
            shot=_text(data.get("shot")),
            file=_text(data.get("file")),
            audio=_text(data.get("audio")),
            source=_text(data.get("source")),
            seconds=_float_value(data.get("seconds")),
            sound=bool(data.get("sound", False)),
            error=_text(data.get("error")),
        )


@dataclass
class ComposedJoin:
    """Where one take meets the take before it."""

    before: str = ""
    after: str = ""
    kind: str = ""
    jump: float = 0.0

    def to_dict(self) -> dict:
        """Return the external JSON shape of this join."""
        return {
            "before": self.before,
            "after": self.after,
            "kind": self.kind,
            "jump": self.jump,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ComposedJoin:
        """Build a join from its external JSON shape."""
        return cls(
            before=_text(data.get("before")),
            after=_text(data.get("after")),
            kind=_text(data.get("kind")),
            jump=_float_value(data.get("jump")),
        )


@dataclass
class BookCompose:
    """Every take of one book, in shot order, and the film they make."""

    id: str = ""
    film: str = ""
    title_card: str = ""
    seconds: float = 0.0
    shots: list[ComposedShot] = field(default_factory=list)
    joins: list[ComposedJoin] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these takes."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "film": self.film,
            "title_card": self.title_card,
            "seconds": self.seconds,
            "shots": [shot.to_dict() for shot in self.shots],
            "joins": [join.to_dict() for join in self.joins],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookCompose:
        """Build the takes from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            film=_text(data.get("film")),
            title_card=_text(data.get("title_card")),
            seconds=_float_value(data.get("seconds")),
            shots=_shot_list(data.get("shots")),
            joins=_join_list(data.get("joins")),
            error=_text(data.get("error")),
        )


# Read a text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read a length in seconds, falling back to zero.
def _float_value(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


# Read the take list, keeping the entries that name a shot.
def _shot_list(value: object) -> list[ComposedShot]:
    if not isinstance(value, list):
        return []
    shots = [
        ComposedShot.from_dict(item)
        for item in value
        if isinstance(item, dict)
    ]
    return [shot for shot in shots if shot.shot]


# Read the join list, keeping the entries that name both sides.
def _join_list(value: object) -> list[ComposedJoin]:
    if not isinstance(value, list):
        return []
    joins = [
        ComposedJoin.from_dict(item)
        for item in value
        if isinstance(item, dict)
    ]
    return [join for join in joins if join.before and join.after]
