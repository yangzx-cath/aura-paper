"""Generate one video clip per page and collect them into a clip set."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .cache import Cache, file_fingerprint, fingerprint
from .config import out_root
from .minimax import MiniMaxClient, MiniMaxError, VideoRequest
from .output import write_json
from .prompts import clip_prompt
from .screenplay import PageScene, Screenplay
from .story import Story
from .understand import BookContent, PageContent
from .utils import now_iso


@dataclass
class VideoClip:
    """One generated video clip for a page."""

    index: int
    filename: str
    prompt: str
    task_id: str = ""
    model: str = ""
    duration: int = 6
    resolution: str = "768P"
    path: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this clip."""
        return {
            "index": self.index,
            "filename": self.filename,
            "model": self.model,
            "generated_at": now_iso(),
            "prompt": self.prompt,
            "task_id": self.task_id,
            "duration": self.duration,
            "resolution": self.resolution,
            "path": self.path,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VideoClip:
        """Build a clip from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            filename=str(data.get("filename") or ""),
            prompt=str(data.get("prompt") or ""),
            task_id=str(data.get("task_id") or ""),
            model=str(data.get("model") or ""),
            duration=int(data.get("duration") or 6),
            resolution=str(data.get("resolution") or "768P"),
            path=str(data.get("path") or ""),
            error=str(data.get("error") or ""),
        )


@dataclass
class BookClips:
    """All generated clips of one book."""

    id: str
    title: str
    source: str
    model: str = ""
    clips: list[VideoClip] = field(default_factory=list)
    error: str = ""

    @property
    def clip_count(self) -> int:
        """Return the number of clips, failed ones included."""
        return len(self.clips)

    @property
    def failed_count(self) -> int:
        """Return how many clips failed."""
        return sum(1 for clip in self.clips if clip.error)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this clip set."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "generated_at": now_iso(),
            "model": self.model,
            "clip_count": self.clip_count,
            "failed_count": self.failed_count,
            "clips": [clip.to_dict() for clip in self.clips],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookClips:
        """Build a clip set from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            source=str(data.get("source") or ""),
            model=str(data.get("model") or ""),
            clips=[
                VideoClip.from_dict(clip)
                for clip in data.get("clips") or []
                if isinstance(clip, dict)
            ],
            error=str(data.get("error") or ""),
        )


def clip_path(
    book_id: str,
    filename: str,
    root: str | Path | None = None,
) -> Path:
    """Return <root>/<book_id>/clips/<image stem>.mp4."""
    return _book_dir(book_id, root) / "clips" / f"{Path(filename).stem}.mp4"


# Return the output directory of one book.
def _book_dir(book_id: str, root: str | Path | None) -> Path:
    base = Path(root) if root is not None else out_root()
    return base / book_id


def generate_clip(
    content: BookContent,
    page: PageContent,
    story: Story,
    scene: PageScene,
    client: MiniMaxClient,
    *,
    root: str | Path | None = None,
    duration: int | None = None,
    resolution: str = "768P",
) -> VideoClip:
    """Generate one page clip and return its metadata."""
    assert scene.index == page.index

    prompt = clip_prompt(page, story, beat=scene.beat)
    seconds = scene.duration if duration is None else duration

    target = clip_path(content.id, page.filename, root)
    clip = VideoClip(
        index=page.index,
        filename=page.filename,
        prompt=prompt,
        model=client.model,
        duration=seconds,
        resolution=resolution,
        path=str(target.relative_to(_book_dir(content.id, root))),
    )

    if scene.error:
        clip.error = scene.error
        return clip

    request = VideoRequest(
        prompt=prompt,
        reference_images=[_page_path(content, page)],
        duration=seconds,
        resolution=resolution,
    )

    try:
        task = client.create_task(request)
        clip.task_id = task.task_id
        task = client.wait_task(task.task_id)
        if not task.succeeded:
            clip.error = task.error or f"task {task.status or 'failed'}"
            return clip
        if not task.video_url:
            clip.error = "task succeeded without a video URL"
            return clip
        client.download(task.video_url, target)
    except (MiniMaxError, ValueError) as exc:
        clip.error = str(exc)
        return clip

    clip.duration = task.duration or seconds
    clip.resolution = task.resolution or resolution
    return clip


# Resolve the source image of one page.
def _page_path(content: BookContent, page: PageContent) -> Path:
    return Path(content.source) / page.filename


def build_clips(
    content: BookContent,
    story: Story,
    screenplay: Screenplay,
    client: MiniMaxClient,
    *,
    cache: Cache | None = None,
    root: str | Path | None = None,
    resolution: str = "768P",
    workers: int = 1,
    on_page: Callable[[PageContent, VideoClip, float], None] | None = None,
) -> BookClips:
    """Generate one clip for every planned scene and collect them."""
    assert workers >= 1

    clip_set = BookClips(
        id=content.id,
        title=content.title,
        source=content.source,
        model=client.model,
    )
    scenes = {scene.index: scene for scene in screenplay.pages}
    tasks = [page for page in content.story_pages if page.index in scenes]

    def run(page: PageContent) -> VideoClip:
        started = time.perf_counter()
        clip = _one_clip(
            content,
            page,
            story,
            scenes[page.index],
            client,
            cache,
            root,
            resolution,
        )
        if on_page is not None:
            on_page(page, clip, time.perf_counter() - started)
        return clip

    if workers == 1:
        clips = [run(page) for page in tasks]
    else:
        # pool.map() keeps the input order, so clips line up with the pages.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            clips = list(pool.map(run, tasks))

    clip_set.clips = clips
    return clip_set


# Reuse a matching clip on disk, otherwise generate one and cache it.
def _one_clip(
    content: BookContent,
    page: PageContent,
    story: Story,
    scene: PageScene,
    client: MiniMaxClient,
    cache: Cache | None,
    root: str | Path | None,
    resolution: str,
) -> VideoClip:
    ns = f"clips/{content.id}"
    name = Path(page.filename).stem
    key = ""

    if cache is not None:
        key = _clip_key(content, page, story, scene, client, resolution)
        entry = cache.load_json(ns, name, key)
        target = clip_path(content.id, page.filename, root)
        if entry is not None and target.is_file():
            return _reused(entry, content, page, root, target)

    clip = generate_clip(
        content, page, story, scene, client, root=root, resolution=resolution
    )
    # Errors are never cached, so a failed clip is retried next run.
    if cache is not None and not clip.error:
        cache.save_json(ns, name, key, clip.to_dict())
    return clip


# Restore a cached clip and refresh the fields that belong to the page.
def _reused(
    entry: dict,
    content: BookContent,
    page: PageContent,
    root: str | Path | None,
    target: Path,
) -> VideoClip:
    clip = VideoClip.from_dict(entry)
    clip.index = page.index
    clip.filename = page.filename
    clip.path = str(target.relative_to(_book_dir(content.id, root)))
    return clip


# Identify one clip request: prompt, page image, length, size and model.
def _clip_key(
    content: BookContent,
    page: PageContent,
    story: Story,
    scene: PageScene,
    client: MiniMaxClient,
    resolution: str,
) -> str:
    prompt = clip_prompt(page, story, beat=scene.beat)
    return fingerprint(
        prompt,
        file_fingerprint(_page_path(content, page)),
        str(scene.duration),
        resolution,
        client.model,
    )


def save_clips(
    clip_set: BookClips,
    root: str | Path | None = None,
) -> Path:
    """Write the clip set to <root>/<id>/clips.json."""
    return write_json(clip_set.id, "clips", clip_set.to_dict(), root)
