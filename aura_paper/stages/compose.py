"""Lay the spoken lines under every rendered clip and mix them together."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from PIL import Image, ImageChops

from ..clients.tts import DEFAULT_RATE
from ..media import ffmpeg
from ..schema.compose import BookCompose, ComposedJoin, ComposedShot
from ..schema.job import BookJobs, Job
from ..store.output import write_json
from .paths import book_dir, shots_dir

# 16-bit mono, so one second holds rate * 2 bytes.
BYTES_PER_FRAME = 2

# The speech client writes a plain header in front of its samples.
WAV_HEADER = 44

# Every take is encoded the same way, so the takes can be joined later.
SUFFIX = ".mp4"
TRACK_SUFFIX = ".wav"

# How long two shots share the screen when they dissolve into each other.
OVERLAP = 0.5

# A shot with no clip yet is expected while the render is still running.
MISSING = "还没有生成这一镜"

# The frames either side of a join are compared at this size.
JUMP_BOX = (64, 64)


def compose(
    book_id: str,
    *,
    only: str = "",
    min_seconds: float = 0.0,
    tail_seconds: float = 0.0,
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
        result.shots.append(
            _one(job, directory, out_dir, min_seconds, tail_seconds)
        )

    result.joins = _joins(job_book.shots, result.shots, out_dir)
    notes = []
    if not only:
        _film(job_book.shots, result, out_dir, notes)
    result.error = "；".join(
        [
            f"{shot.shot}：{shot.error}"
            for shot in result.shots
            if shot.error and shot.error != MISSING
        ]
        + notes
    )
    write_json(book_id, "compose", result.to_dict(), root)
    return result


# Mix one shot, or record why it could not be done.
def _one(
    job: Job,
    directory: Path,
    out_dir: Path,
    min_seconds: float,
    tail_seconds: float,
) -> ComposedShot:
    record = ComposedShot(shot=job.shot)
    source = f"clips/{job.shot}{SUFFIX}"
    clip = directory / source
    if not clip.is_file():
        record.error = MISSING
        return record

    record.source = source
    try:
        info = ffmpeg.probe(clip)
    except ffmpeg.FFmpegError as exc:
        record.error = str(exc)
        return record
    record.sound = info.has_audio

    seconds = _seconds(job, info.duration_ms, min_seconds, tail_seconds)
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


# Take the shot as long as its lines run plus a tail, so the picture holds a
# moment after the last word instead of butting into the next shot. A shot
# with nothing spoken keeps the whole clip, and no take runs past its clip.
def _seconds(
    job: Job,
    clip_ms: int,
    min_seconds: float,
    tail_seconds: float,
) -> float:
    clip = clip_ms / 1000
    if not any(line.file for line in job.lines):
        return round(clip, 3)
    wanted = max(job.audio_ms / 1000 + tail_seconds, min_seconds)
    return round(min(clip, wanted), 3)


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


# Measure every join between two takes that are both on disk.
def _joins(
    jobs: list[Job],
    takes: list[ComposedShot],
    out_dir: Path,
) -> list[ComposedJoin]:
    found = {take.shot: take for take in takes if take.file}
    joins = []
    for number, job in enumerate(jobs[:-1]):
        after = jobs[number + 1]
        if job.shot not in found or after.shot not in found:
            continue
        joins.append(
            ComposedJoin(
                before=job.shot,
                after=after.shot,
                kind=after.join,
                jump=round(
                    _jump(
                        out_dir / f"{job.shot}{SUFFIX}",
                        out_dir / f"{after.shot}{SUFFIX}",
                        out_dir,
                    ),
                    1,
                ),
            )
        )
    return joins


# Compare the last picture of one take with the first of the next.
def _jump(before: Path, after: Path, folder: Path) -> float:
    first = ffmpeg.frame(before, folder / "tail.jpg", last=True)
    second = ffmpeg.frame(after, folder / "head.jpg")
    left = Image.open(first).convert("L").resize(JUMP_BOX)
    right = Image.open(second).convert("L").resize(JUMP_BOX)
    data = ImageChops.difference(left, right).tobytes()
    return sum(data) / len(data)


# Join every take into one film, once all of them are on disk.
def _film(
    jobs: list[Job],
    result: BookCompose,
    out_dir: Path,
    notes: list[str],
) -> None:
    takes = [take for take in result.shots if take.file]
    if len(takes) != len(jobs):
        notes.append(f"还有 {len(jobs) - len(takes)} 镜没出片，先不拼整片")
        return
    if not takes:
        return

    paths = [out_dir / f"{job.shot}{SUFFIX}" for job in jobs]
    overlaps = [OVERLAP if job.join == "叠化" else 0.0 for job in jobs[1:]]
    target = out_dir / f"film{SUFFIX}"
    try:
        ffmpeg.join(paths, target, overlaps=overlaps)
    except ffmpeg.FFmpegError as exc:
        notes.append(f"整片拼接失败：{exc}")
        return
    result.film = f"shots/{target.name}"
    result.seconds = round(ffmpeg.probe(target).duration_ms / 1000, 2)


# Read the jobs stage's record of the shots.
def _read_jobs(directory: Path) -> BookJobs:
    path = directory / "jobs.json"
    return BookJobs.from_dict(json.loads(path.read_text("utf-8")))
