"""Assemble one silent track with the spoken parts pasted in."""

from __future__ import annotations

import struct
from pathlib import Path

from ..clients.tts import DEFAULT_RATE

# 16-bit mono, so one second holds rate * 2 bytes.
BYTES_PER_FRAME = 2

# The speech client writes a plain header in front of its samples.
WAV_HEADER = 44


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
