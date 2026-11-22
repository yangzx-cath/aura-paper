"""The audio of one book and the voices it can be spoken with."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso

# Ids and what each one sounds like, from the 豆包语音合成模型2.0 list.
CHOICES = (
    ("zh_female_zhixingnv_uranus_bigtts", "成年女声，清楚平实，像女老师"),
    ("zh_female_shaoergushi_uranus_bigtts", "成年女声，绘本故事的讲法"),
    ("zh_female_wenroumama_uranus_bigtts", "成年女声，温柔，像妈妈"),
    ("zh_male_wennuanahu_uranus_bigtts", "成年男声，温暖，像爸爸"),
    ("zh_male_chunhoudiyin_uranus_bigtts", "成年男声，低沉"),
    ("zh_female_xiaoxue_uranus_bigtts", "女童，绘本童声"),
    ("zh_female_yingtaowanzi_uranus_bigtts", "女童，活泼跳脱"),
    ("zh_male_naiqimengwa_uranus_bigtts", "男童，奶气"),
    ("zh_male_tiancaitongsheng_uranus_bigtts", "男童，清亮"),
)

# Every line that is not a character's is spoken with this voice.
NARRATOR = "zh_female_zhixingnv_uranus_bigtts"

# Every id a character may be given.
ALL = frozenset(voice for voice, _ in CHOICES)


@dataclass
class VoiceLine:
    """One line of a shot, turned into audio."""

    index: int = 0
    kind: str = ""
    cast: str = ""
    text: str = ""
    spoken: str = ""
    voice: str = ""
    file: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        """Return the external JSON shape of this line."""
        return {
            "index": self.index,
            "kind": self.kind,
            "cast": self.cast,
            "text": self.text,
            "spoken": self.spoken,
            "voice": self.voice,
            "file": self.file,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VoiceLine:
        """Build a line from its external JSON shape."""
        return cls(
            index=_int_value(data.get("index")),
            kind=_text(data.get("kind")),
            cast=_text(data.get("cast")),
            text=_text(data.get("text")),
            spoken=_text(data.get("spoken")),
            voice=_text(data.get("voice")),
            file=_text(data.get("file")),
            duration_ms=_int_value(data.get("duration_ms")),
        )


@dataclass
class VoiceShot:
    """The sound of one shot, and how long the clip has to be."""

    shot: str = ""
    gap_ms: int = 0
    duration_ms: int = 0
    lines: list[VoiceLine] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this shot."""
        return {
            "shot": self.shot,
            "gap_ms": self.gap_ms,
            "duration_ms": self.duration_ms,
            "lines": [line.to_dict() for line in self.lines],
        }

    @classmethod
    def from_dict(cls, data: dict) -> VoiceShot:
        """Build a shot from its external JSON shape."""
        return cls(
            shot=_text(data.get("shot")),
            gap_ms=_int_value(data.get("gap_ms")),
            duration_ms=_int_value(data.get("duration_ms")),
            lines=_line_list(data.get("lines")),
        )


@dataclass
class BookVoice:
    """All the audio of one book."""

    id: str = ""
    resource_id: str = ""
    voices: dict[str, str] = field(default_factory=dict)
    shots: list[VoiceShot] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book's audio."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "resource_id": self.resource_id,
            "voices": self.voices,
            "shots": [shot.to_dict() for shot in self.shots],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookVoice:
        """Build the audio from its external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            resource_id=_text(data.get("resource_id")),
            voices=_text_map(data.get("voices")),
            shots=_shot_list(data.get("shots")),
            error=_text(data.get("error")),
        )


# Read every text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read an integer, falling back to zero when the value is unusable.
def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read a mapping of speaker to voice, dropping the empty entries.
def _text_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    pairs = ((_text(name), _text(voice)) for name, voice in value.items())
    return {name: voice for name, voice in pairs if name and voice}


# Read the lines of one shot, keeping entries that name a file.
def _line_list(value: object) -> list[VoiceLine]:
    if not isinstance(value, list):
        return []
    items = [
        VoiceLine.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.file]


# Read the shot list, keeping entries that name a shot.
def _shot_list(value: object) -> list[VoiceShot]:
    if not isinstance(value, list):
        return []
    items = [
        VoiceShot.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.shot]
