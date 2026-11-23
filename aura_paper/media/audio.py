"""Assemble one track from the spoken parts, and read what a track holds."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from ..clients.tts import DEFAULT_RATE
from . import ffmpeg

# 16-bit mono, so one second holds rate * 2 bytes.
BYTES_PER_FRAME = 2

# The speech client writes a plain header in front of its samples.
WAV_HEADER = 44

# The window one mark covers, and how loud a window must be to count as sound.
STEP = 0.05
FLOOR = 1500

# The edge of a window is left out, because speech trails over the seams.
MARGIN_MS = 200

# The edge of a window is left out, because speech trails over the seams.
MARGIN_MS = 200


def write_track(
    target: Path,
    parts: list[tuple[int, Path]],
    seconds: float,
) -> None:
    """Write a silent track of the given length with every part pasted in.

    Each part is a start in milliseconds and the WAV it starts with. A part
    missing on disk is skipped and one running past the end is cut, so the
    track is always exactly as long as asked.
    """
    samples = bytearray(b"\x00\x00" * int(DEFAULT_RATE * seconds))
    for start_ms, path in parts:
        if not path.is_file():
            continue
        start = start_ms * DEFAULT_RATE // 1000 * BYTES_PER_FRAME
        audio = path.read_bytes()[WAV_HEADER:]
        room = max(0, len(samples) - start)
        samples[start : start + len(audio)] = audio[:room]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_wav(bytes(samples)))


def sound_in_windows(path: Path, windows: list[tuple[int, int]]) -> float:
    """Return how many seconds of a track carry sound inside the windows.

    Each window is a start and an end in milliseconds. A model that speaks
    where the shot has no words is doing something the shot never asked for,
    so the caller can report it.
    """
    marks = _marks(path)
    found = 0
    for start_ms, end_ms in windows:
        first = max(0, int((start_ms + MARGIN_MS) / 1000 / STEP))
        last = min(len(marks), int((end_ms - MARGIN_MS) / 1000 / STEP))
        found += sum(1 for index in range(first, last) if marks[index])
    return round(found * STEP, 2)


def extract(clip: Path, target: Path) -> None:
    """Write the sound of a video clip as the WAV the marks are read from."""
    target.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            ffmpeg.FFMPEG,
            *ffmpeg.COMMON,
            "-i",
            str(clip),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(DEFAULT_RATE),
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )


# Return one mark per step, True where the track carries sound.
def _marks(path: Path) -> list[bool]:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        data = handle.readframes(handle.getnframes())
    samples = memoryview(data).cast("h")
    size = int(rate * STEP)
    return [
        max((abs(value) for value in samples[at : at + size]), default=0)
        > FLOOR
        for at in range(0, len(samples), size)
    ]


# Wrap raw samples in a WAV container.
def _wav(pcm: bytes) -> bytes:
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack(
        "<IHHIIHH",
        16,
        1,
        1,
        DEFAULT_RATE,
        DEFAULT_RATE * BYTES_PER_FRAME,
        BYTES_PER_FRAME,
        16,
    )
    return header + b"data" + struct.pack("<I", len(pcm)) + pcm
