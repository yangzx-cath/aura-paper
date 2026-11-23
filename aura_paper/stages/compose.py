"""Lay the spoken lines under every rendered clip and mix them together."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from ..clients.tts import DEFAULT_RATE
from ..media import ffmpeg
from ..output import write_json
from ..schema.compose import BookCompose, ComposedShot
from ..schema.job import BookJobs, Job
from .paths import book_dir, shots_dir

# 16-bit mono, so one second holds rate * 2 bytes.
BYTES_PER_FRAME = 2

# The speech client writes a plain header in front of its samples.
WAV_HEADER = 44

# Every take is encoded the same way, so the takes can be joined later.
SUFFIX = ".mp4"
TRACK_SUFFIX = ".wav"


def compose(
    book_id: str,
    *,
    only: str = "",
    root: str | Path | None = None,
) -> BookCompose:
    """Read jobs.json, mix one take per shot, write compose.json."""
    directory = book_dir(book_id, root)
    job_book = _read_jobs(directory)
    out_dir = shots_dir(book_id, root)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = BookCompose(id=book_id)
    for job in job_book.shots:
        if only and job.shot != only:
            continue
        result.shots.append(_one(job, directory, out_dir))

    result.error = "；".join(
        f"{shot.shot}：{shot.error}" for shot in result.shots if shot.error
    )
    write_json(book_id, "compose", result.to_dict(), root)
    return result


# Mix one shot, or record why it could not be done.
def _one(job: Job, directory: Path, out_dir: Path) -> ComposedShot:
    record = ComposedShot(shot=job.shot)
    source = f"clips/{job.shot}{SUFFIX}"
    clip = directory / source
    if not clip.is_file():
        record.error = "还没有生成这一镜"
        return record

    record.source = source
    try:
        info = ffmpeg.probe(clip)
    except ffmpeg.FFmpegError as exc:
        record.error = str(exc)
        return record
    record.sound = info.has_audio

    seconds = _seconds(job, info.duration_ms)
    track = out_dir / f"{job.shot}{TRACK_SUFFIX}"
    _write_track(track, job, seconds, directory)
    record.audio = f"shots/{track.name}"

    target = out_dir / f"{job.shot}{SUFFIX}"
    try:
        if info.has_audio:
            ffmpeg.mix(clip, track, target, seconds=seconds)
        else:
            ffmpeg.mux(clip, track, target, seconds=seconds)
    except ffmpeg.FFmpegError as exc:
        record.error = str(exc)
        return record

    record.file = f"shots/{target.name}"
    record.seconds = round(seconds, 3)
    return record


# Take the shot as long as its lines run, or as long as the clip when the
# shot has nothing spoken: a sound effect alone must not cut the picture.
def _seconds(job: Job, clip_ms: int) -> float:
    if not any(line.file for line in job.lines):
        return round(clip_ms / 1000, 3)
    return round(job.audio_ms / 1000, 3)


# Write one track with every line pasted at the offset jobs.json gives.
def _write_track(
    target: Path,
    job: Job,
    seconds: float,
    directory: Path,
) -> None:
    samples = bytearray(_silence(seconds))
    for line in job.lines:
        if not line.file:
            continue
        source = directory / line.file
        if not source.is_file():
            continue
        start = line.start_ms * DEFAULT_RATE // 1000 * BYTES_PER_FRAME
        audio = source.read_bytes()[WAV_HEADER:]
        room = max(0, len(samples) - start)
        samples[start : start + len(audio)] = audio[:room]
    _write_wav(target, bytes(samples))


# Return a silent track of the given length.
def _silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(DEFAULT_RATE * seconds)


# Wrap raw samples in a WAV container.
def _write_wav(path: Path, pcm: bytes) -> None:
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
    header += b"data" + struct.pack("<I", len(pcm))
    path.write_bytes(header + pcm)


# Read the jobs stage's record of the shots.
def _read_jobs(directory: Path) -> BookJobs:
    path = directory / "jobs.json"
    return BookJobs.from_dict(json.loads(path.read_text("utf-8")))
