"""Generate one video clip per page and collect them into a book video."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import out_root
from .minimax import MiniMaxClient, MiniMaxError, VideoRequest
from .prompts import shot_prompt

if TYPE_CHECKING:
    from .cache import Cache
    from .story import Story
    from .understand import BookContent, PageContent


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
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> VideoClip:
        """Build a clip from its external JSON shape."""
        raise NotImplementedError


@dataclass
class BookVideo:
    """All generated clips of one book."""

    id: str
    title: str
    source: str
    model: str = ""
    clips: list[VideoClip] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book video."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> BookVideo:
        """Build a book video from its external JSON shape."""
        raise NotImplementedError


def clip_path(
    book_id: str,
    index: int,
    root: str | Path | None = None,
) -> Path:
    """Return <root>/<book_id>/clips/page_01.mp4."""
    name = f"page_{index + 1:02d}.mp4"
    return _book_dir(book_id, root) / "clips" / name


# Return the output directory of one book.
def _book_dir(book_id: str, root: str | Path | None) -> Path:
    base = Path(root) if root is not None else out_root()
    return base / book_id


def generate_clip(
    content: BookContent,
    page: PageContent,
    story: Story,
    client: MiniMaxClient,
    *,
    root: str | Path | None = None,
    duration: int = 6,
    resolution: str = "768P",
) -> VideoClip:
    """Generate one page clip and return its metadata."""
    prompt = shot_prompt(page, story)

    target = clip_path(content.id, page.index, root)
    request = VideoRequest(
        prompt=prompt,
        first_frame=_page_path(content, page),
        duration=duration,
        resolution=resolution,
    )
    clip = VideoClip(
        index=page.index,
        filename=page.filename,
        prompt=prompt,
        model=client.model,
        duration=duration,
        resolution=resolution,
        path=str(target.relative_to(_book_dir(content.id, root))),
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
    except (MiniMaxError, ValueError, OSError) as exc:
        clip.error = str(exc)
        return clip

    clip.duration = task.duration or duration
    clip.resolution = task.resolution or resolution
    return clip


# Resolve the source image of one page.
def _page_path(content: BookContent, page: PageContent) -> Path:
    return Path(content.source) / page.filename


def build_video(
    content: BookContent,
    story: Story,
    client: MiniMaxClient,
    *,
    cache: Cache | None = None,
    root: str | Path | None = None,
    workers: int = 1,
) -> BookVideo:
    """Generate every page clip and return the book video."""
    raise NotImplementedError


def save_video(
    video: BookVideo,
    root: str | Path | None = None,
) -> Path:
    """Write the book video to <root>/<id>/video.json."""
    raise NotImplementedError
