"""Generate one video clip per shot and record how each run went."""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..cache import Cache, file_fingerprint, fingerprint
from ..clients.video import VideoClient, VideoError, VideoRequest
from ..output import write_json
from ..schema.job import BookJobs, Job
from ..schema.render import BookRender, ShotRender
from .paths import book_dir, clips_dir

# What each generated clip is saved as.
CLIP_SUFFIX = ".mp4"


def render(
    book_id: str,
    *,
    client: VideoClient,
    only: str = "",
    root: str | Path | None = None,
    cache: Cache | None = None,
) -> BookRender:
    """Read jobs.json, generate every clip, write render.json."""
    directory = book_dir(book_id, root)
    job_book = _read_jobs(directory)
    out_dir = clips_dir(book_id, root)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = BookRender(id=book_id, model=client.model)
    for job in job_book.shots:
        if only and job.shot != only:
            continue
        result.shots.append(
            _render_one(job, directory, out_dir, client, cache)
        )

    result.error = "；".join(
        f"{shot.shot}：{shot.error}" for shot in result.shots if shot.error
    )
    write_json(book_id, "render", result.to_dict(), root)
    return result


# Generate one clip, reusing the cached video when the job did not change.
def _render_one(
    job: Job,
    directory: Path,
    out_dir: Path,
    client: VideoClient,
    cache: Cache | None,
) -> ShotRender:
    target = out_dir / f"{job.shot}{CLIP_SUFFIX}"
    record = ShotRender(
        shot=job.shot,
        file=f"clips/{target.name}",
        resolution=job.resolution,
    )
    if job.error:
        record.error = job.error
        return record

    images = [directory / image.file for image in job.images]
    key = _key(job, images, client)
    saved = _cached(key, cache)
    if saved is not None:
        _copy(saved, target)
        record.cached = True
        return record

    started = time.perf_counter()
    task = None
    try:
        # VideoRequest checks the length and the images, so it sits inside.
        request = VideoRequest(
            prompt=job.prompt,
            reference_images=images,
            duration=job.duration,
            resolution=job.resolution,
            ratio=job.ratio,
            generate_audio=job.audio,
        )
        task = client.generate(request, target)
    except (VideoError, ValueError) as exc:
        record.error = str(exc)
        return record
    finally:
        record.seconds = round(time.perf_counter() - started, 1)

    record.task_id = task.task_id
    record.duration = task.duration or job.duration
    record.resolution = task.resolution or job.resolution
    if not task.succeeded:
        record.error = task.error or f"task {task.status or 'failed'}"
        return record
    _keep(target, key, cache)
    return record


# Return the cached video of one job, when it is still on disk.
def _cached(key: str, cache: Cache | None) -> Path | None:
    if cache is None or not cache.enabled:
        return None
    path = cache.file_path("render", key, CLIP_SUFFIX)
    return path if path.is_file() else None


# Keep a finished clip in the cache, so a rerun costs nothing.
def _keep(target: Path, key: str, cache: Cache | None) -> None:
    if cache is None or not cache.enabled:
        return
    _copy(target, cache.file_path("render", key, CLIP_SUFFIX))


# Copy one file over another, making the folder first.
def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


# Fingerprint the job, its images and the model, so the key is exact.
def _key(job: Job, images: list[Path], client: VideoClient) -> str:
    digests = [file_fingerprint(path) for path in images]
    return fingerprint(
        job.prompt,
        *digests,
        job.duration,
        job.ratio,
        job.resolution,
        job.audio,
        client.model,
    )


# Read the jobs stage's record of the shots.
def _read_jobs(directory: Path) -> BookJobs:
    path = directory / "jobs.json"
    return BookJobs.from_dict(json.loads(path.read_text("utf-8")))
