"""The subtitle file of one book and the copy of the film that carries it."""

from __future__ import annotations

from dataclasses import dataclass

from .time import now_iso


@dataclass
class BookSubtitles:
    """Every spoken line placed on the finished film."""

    id: str = ""
    file: str = ""
    vtt: str = ""
    burned: str = ""
    cues: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this subtitle file."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "file": self.file,
            "vtt": self.vtt,
            "burned": self.burned,
            "cues": self.cues,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookSubtitles:
        """Build a subtitle record from its external JSON shape."""
        return cls(
            id=str(data.get("id") or "").strip(),
            file=str(data.get("file") or "").strip(),
            vtt=str(data.get("vtt") or "").strip(),
            burned=str(data.get("burned") or "").strip(),
            cues=int(data.get("cues") or 0),
            error=str(data.get("error") or "").strip(),
        )
