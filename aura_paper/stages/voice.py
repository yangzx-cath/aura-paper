"""Turn every line of a shot into audio, and measure the shot."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..cache import Cache, fingerprint
from ..clients.tts import DEFAULT_RATE, TTSClient, TTSError
from ..output import write_json
from ..schema.cast import BookCast
from ..schema.shot import BookShots, Shot
from ..schema.voice import NARRATOR, BookVoice, VoiceLine, VoiceShot
from .paths import book_dir, voice_dir

# A short rest between two lines of the same shot.
DEFAULT_GAP_MS = 300

# Bytes of the WAV header the client puts in front of the samples.
WAV_HEADER = 44

# 16-bit mono, so one second holds rate * 2 bytes.
BYTES_PER_FRAME = 2

# What the spoken audio is saved as.
FILE_SUFFIX = ".wav"


def voice(
    book_id: str,
    *,
    tts: TTSClient,
    overrides: dict[str, str] | None = None,
    speeds: dict[str, float] | None = None,
    gap_ms: int = DEFAULT_GAP_MS,
    root: str | Path | None = None,
    cache: Cache | None = None,
) -> BookVoice:
    """Read shots.json, speak every line, write voice.json and the audio."""
    directory = book_dir(book_id, root)
    shots = _read_shots(directory).shots
    voices = voices_for(book_id, overrides=overrides, root=root)
    rates = dict(speeds or {})

    result = BookVoice(
        id=book_id,
        resource_id=tts.resource_id,
        voices=dict(voices),
        error="",
    )
    missing = _missing_voices(shots, voices)
    if missing:
        result.error = "没有说话人的音色：" + "、".join(missing)
        write_json(book_id, "voice", result.to_dict(), root)
        return result

    out_dir = voice_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)

    for shot in shots:
        record = VoiceShot(shot=shot.id, gap_ms=gap_ms)
        try:
            record.lines = _speak_shot(
                shot, out_dir, tts, voices, rates, cache
            )
        except TTSError as exc:
            result.error = f"{shot.id} 配音失败：{exc}"
            break
        record.duration_ms = _shot_length(record.lines, gap_ms)
        result.shots.append(record)

    write_json(book_id, "voice", result.to_dict(), root)
    return result


# Read the voice of every speaker from cast.json, then apply the overrides.
def voices_for(
    book_id: str,
    *,
    overrides: dict[str, str] | None = None,
    root: str | Path | None = None,
) -> dict[str, str]:
    """Return the voice of every speaker the cast stage named."""
    cast_book = _read_cast(book_dir(book_id, root))
    voices = {"旁白": NARRATOR}
    for member in cast_book.cast:
        if member.voice:
            voices[member.id] = member.voice
    voices.update(overrides or {})
    return voices


# List the speakers that have no voice yet, so nothing is spoken twice.
def _missing_voices(shots: list[Shot], voices: dict[str, str]) -> list[str]:
    missing = []
    for shot in shots:
        for line in shot.audio:
            speaker = _speaker(line.kind, line.cast)
            if speaker and not voices.get(speaker) and speaker not in missing:
                missing.append(speaker)
    return missing


# Return the speaker of a line, or an empty name for a sound effect.
def _speaker(kind: str, cast: str) -> str:
    if kind == "旁白":
        return "旁白"
    if kind == "对白":
        return cast
    return ""


# Speak every audible line of one shot.
def _speak_shot(
    shot: Shot,
    out_dir: Path,
    tts: TTSClient,
    voices: dict[str, str],
    rates: dict[str, float],
    cache: Cache | None,
) -> list[VoiceLine]:
    spoken = []
    for index, line in enumerate(shot.audio):
        speaker = _speaker(line.kind, line.cast)
        if not speaker:
            continue
        text = line.spoken or line.text
        if not text:
            continue
        voice_id = voices[speaker]
        speed = rates.get(speaker, 1.0)
        target = out_dir / f"{shot.id}-{index}{FILE_SUFFIX}"
        _speak(text, voice_id, speed, target, tts, cache)
        spoken.append(
            VoiceLine(
                index=index,
                kind=line.kind,
                cast=line.cast,
                text=line.text,
                spoken=text,
                voice=voice_id,
                speed=speed,
                file=f"voice/{target.name}",
                duration_ms=_file_length(target),
            )
        )
    return spoken


# Speak one line into target, reusing the cached audio when it exists.
def _speak(
    text: str,
    voice_id: str,
    speed: float,
    target: Path,
    tts: TTSClient,
    cache: Cache | None,
) -> None:
    key = fingerprint(text, voice_id, speed, *tts.signature)
    if cache is not None:
        cached = cache.file_path("voice", key, FILE_SUFFIX)
        if cache.enabled and cached.is_file():
            _copy(cached, target)
            return

    speech = tts.synthesize(text, voice=voice_id, speed=speed)
    speech.save(target)
    if cache is not None and cache.enabled:
        _copy(target, cache.file_path("voice", key, FILE_SUFFIX))


# Copy one file over another, making the folder first.
def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


# Return how long a spoken line lasts, read off the file it was saved in.
def _file_length(path: Path) -> int:
    size = max(0, path.stat().st_size - WAV_HEADER)
    return round(size * 1000 / (DEFAULT_RATE * BYTES_PER_FRAME))


# Return how long a shot lasts with a rest between its lines.
def _shot_length(lines: list[VoiceLine], gap_ms: int) -> int:
    if not lines:
        return 0
    spoken = sum(line.duration_ms for line in lines)
    return spoken + gap_ms * (len(lines) - 1)


# Read the storyboard's record of the shots.
def _read_shots(directory: Path) -> BookShots:
    path = directory / "shots.json"
    text = path.read_text(encoding="utf-8")
    return BookShots.from_dict(json.loads(text))


# Read the cast stage's record of the characters.
def _read_cast(directory: Path) -> BookCast:
    path = directory / "cast.json"
    text = path.read_text(encoding="utf-8")
    return BookCast.from_dict(json.loads(text))
