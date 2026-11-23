"""The audio of one book and the voices it can be spoken with."""

from __future__ import annotations

from dataclasses import dataclass, field

from .time import now_iso

# Chinese ids and what each one sounds like, from the Seed TTS 2.0 list.
CHINESE_CHOICES = (
    ("zh_female_shaoergushi_uranus_bigtts", "成年女声，讲绘本故事，语速稳"),
    ("zh_female_wenroumama_uranus_bigtts", "成年女声，温柔，像妈妈"),
    ("zh_female_wenroushunv_uranus_bigtts", "成年女声，平缓，像有声书"),
    ("zh_male_wennuanahu_uranus_bigtts", "成年男声，温暖，像爸爸"),
    ("zh_male_chunhoudiyin_uranus_bigtts", "成年男声，低沉"),
    ("zh_female_yingtaowanzi_uranus_bigtts", "女童，活泼跳脱"),
    ("zh_female_peiqi_uranus_bigtts", "女童，卡通感强，鼻音重"),
    ("zh_male_naiqimengwa_uranus_bigtts", "男童，奶气"),
    ("zh_male_liangsangmengzai_uranus_bigtts", "男童，清亮"),
)

# English ids from the same list. A book is spoken in one language, so its
# dialogue and narration stay inside that language's table. Voices marked
# Context only work on the unidirectional call this project makes.
ENGLISH_CHOICES = (
    ("en_female_joanne_uranus_bigtts", "美式英语，成年女声，有声阅读"),
    ("en_female_dacey_uranus_bigtts", "美式英语，成年女声，通用"),
    ("en_female_stokie_uranus_bigtts", "美式英语，成年女声，通用"),
    ("en_female_hayley_uranus_bigtts", "美式英语，成年女声，教学与配音"),
    ("en_female_myra_uranus_bigtts", "美式英语，成年女声，教学"),
    ("en_female_jane_uranus_bigtts", "美式英语，成年女声，视频配音"),
    ("en_female_jenny_uranus_bigtts", "美式英语，成年女声，通用"),
    ("en_female_allison_uranus_bigtts", "美式英语，成年女声，视频配音"),
    ("en_female_skye_uranus_bigtts", "美式英语，成年女声，通用"),
    ("en_female_rachel_p1_uranus_bigtts", "美式英语，成年女声，口音"),
    ("en_female_pleasant-female_uranus_bigtts", "美式英语，成年女声，温和"),
    (
        "en_female_authoritative-british_uranus_bigtts",
        "英式英语，成年女声，教学与配音",
    ),
    ("en_male_tim_uranus_bigtts", "美式英语，成年男声，通用"),
    ("en_male_josh_uranus_bigtts", "美式英语，成年男声，视频配音"),
    ("en_male_jamie_uranus_bigtts", "美式英语，成年男声，教学与配音"),
    ("en_male_kevin_uranus_bigtts", "美式英语，成年男声，教学与配音"),
    ("en_male_alex_uranus_bigtts", "美式英语，成年男声，视频配音"),
    ("en_male_alberto_uranus_bigtts", "美式英语，成年男声，教学"),
    ("en_male_marcus_uranus_bigtts", "美式英语，成年男声，有声阅读"),
    ("en_male_david_uranus_bigtts", "美式英语，成年男声，有声阅读"),
    ("en_male_ryan_uranus_bigtts", "美式英语，成年男声，有声阅读"),
    ("en_male_deep-voice_uranus_bigtts", "美式英语，成年男声，低沉"),
    ("en_male_russell_uranus_bigtts", "英式英语，成年男声，通用"),
    ("en_male_knightley_uranus_bigtts", "英式英语，成年男声，有声阅读"),
)

# Every line that is not a character's is spoken with this voice.
NARRATOR = "zh_female_shaoergushi_uranus_bigtts"

# The narrator of an English book.
ENGLISH_NARRATOR = "en_female_joanne_uranus_bigtts"

# The voices each book language may use, and how each language narrates.
# A question is answered in the language it was asked in, with the narrator
# voice, so the answer never changes character mid-sentence.
CHOICES_BY_LANGUAGE = {
    "zh": CHINESE_CHOICES,
    "en": ENGLISH_CHOICES,
}
NARRATOR_BY_LANGUAGE = {
    "zh": NARRATOR,
    "en": ENGLISH_NARRATOR,
}


# Return the narrator voice of a language, defaulting to Chinese.
def narrator_for(language: str) -> str:
    """Return the narrator voice of a language."""
    return NARRATOR_BY_LANGUAGE.get(language, NARRATOR)


# Every id a character may be given, in either language.
ALL = frozenset(voice for voice, _ in CHINESE_CHOICES + ENGLISH_CHOICES)


@dataclass
class VoiceLine:
    """One line of a shot, turned into audio."""

    index: int = 0
    kind: str = ""
    cast: str = ""
    text: str = ""
    spoken: str = ""
    voice: str = ""
    speed: float = 1.0
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
            "speed": self.speed,
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
            speed=_speed(data.get("speed")),
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


# Read a speed multiplier, falling back to normal speed.
def _speed(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0


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
