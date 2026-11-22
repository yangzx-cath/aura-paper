"""Plan every story page as a scene with a beat and lines."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Callable

from .cache import Cache, fingerprint
from .llm import LLMClient, LLMError
from .output import write_json
from .prompts1 import page_characters, screenplay_prompt
from .story import Story
from .understand import BookContent, PageContent
from .utils import extract_json, now_iso

LINE_KINDS = ("narration", "dialogue")

# A single MiniMax clip lasts between these two limits, in seconds.
MIN_DURATION = 4
MAX_DURATION = 15

DEFAULT_DURATION = 6

# Rough reading speeds, in characters per second.
_CHINESE_PER_SECOND = 4.0
_ENGLISH_PER_SECOND = 12.0


@dataclass
class Line:
    """One spoken line of a page."""

    kind: str
    text: str
    speaker: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this line."""
        return {
            "kind": self.kind,
            "text": self.text,
            "speaker": self.speaker,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Line:
        """Build a line from its external JSON shape."""
        return cls(
            kind=_line_kind(data.get("kind")),
            text=str(data.get("text") or ""),
            speaker=str(data.get("speaker") or ""),
        )


# Keep a line kind inside the supported set, defaulting to narration.
def _line_kind(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in LINE_KINDS else "narration"


@dataclass
class PageScene:
    """Beat, lines, duration and transition of one page."""

    index: int
    beat: str = ""
    lines: list[Line] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    duration: int = DEFAULT_DURATION  # Clip length asked for by the model.
    transition: str = "cut"
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this scene."""
        return {
            "index": self.index,
            "beat": self.beat,
            "lines": [line.to_dict() for line in self.lines],
            "characters": self.characters,
            "duration": self.duration,
            "transition": self.transition,
            "model": self.model,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PageScene:
        """Build a scene from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            beat=str(data.get("beat") or ""),
            lines=_line_list(data.get("lines")),
            characters=_name_list(data.get("characters")),
            duration=int(data.get("duration") or DEFAULT_DURATION),
            transition=str(data.get("transition") or "cut"),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


# Read the line list, skipping entries that are not objects.
def _line_list(value: object) -> list[Line]:
    if not isinstance(value, list):
        return []
    return [Line.from_dict(item) for item in value if isinstance(item, dict)]


# Read a list of character names, dropping empty entries.
def _name_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


@dataclass
class Screenplay:
    """Scenes of a whole book, one per page."""

    id: str = ""
    pages: list[PageScene] = field(default_factory=list)
    model: str = ""
    error: str = ""

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this screenplay."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "page_count": self.page_count,
            "pages": [page.to_dict() for page in self.pages],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Screenplay:
        """Build a screenplay from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            pages=_page_list(data.get("pages")),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


# Read the scene list, skipping entries that are not objects.
def _page_list(value: object) -> list[PageScene]:
    if not isinstance(value, list):
        return []
    return [
        PageScene.from_dict(item) for item in value if isinstance(item, dict)
    ]


def build_screenplay(
    content: BookContent,
    story: Story,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    workers: int = 1,
    on_page: Callable[[PageContent, PageScene, float], None] | None = None,
) -> Screenplay:
    """Write the beat and lines of every story page."""
    assert workers >= 1

    screenplay = Screenplay(id=content.id, model=client.model)
    pages = content.story_pages

    def run(page: PageContent) -> PageScene:
        started = time.perf_counter()
        scene = _build_scene(page, content, story, client, cache)
        if on_page is not None:
            on_page(page, scene, time.perf_counter() - started)
        return scene

    if workers == 1:
        scenes = [run(page) for page in pages]
    else:
        # pool.map() keeps the input order, so scenes line up with the pages.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            scenes = list(pool.map(run, pages))

    screenplay.pages = scenes
    return screenplay


# Ask the model for one page, reusing the cache when its prompt is unchanged.
def _build_scene(
    page: PageContent,
    content: BookContent,
    story: Story,
    client: LLMClient,
    cache: Cache | None,
) -> PageScene:
    scene = PageScene(index=page.index, model=client.model)
    scene.characters = page_characters(page, story)
    prompt = screenplay_prompt(page, content, story)

    if cache is None:
        scene = _request_scene(scene, client, prompt)
        return _finish_scene(scene)

    ns = f"screenplay/{content.id}"
    name = Path(page.filename).stem
    key = fingerprint(prompt, *client.signature)

    entry = cache.load_json(ns, name, key)
    if entry is not None:
        _apply_scene(scene, entry)
        return _finish_scene(scene)

    scene = _request_scene(scene, client, prompt)
    # Errors are never cached, so a broken page is retried next run.
    if not scene.error:
        cache.save_json(ns, name, key, _scene_fields(scene))
    return _finish_scene(scene)


# Call the model for one page and fill the scene fields.
def _request_scene(
    scene: PageScene,
    client: LLMClient,
    prompt: str,
) -> PageScene:
    try:
        reply = client.chat(prompt)
        fields = extract_json(reply)
    except (LLMError, ValueError) as exc:
        scene.error = str(exc)
        return scene

    _apply_scene(scene, fields)
    # A silent page is a real choice, so only the beat is required.
    if not scene.beat:
        scene.error = "model returned no beat"
    return scene


# Copy the scene fields, ignoring missing or malformed values.
def _apply_scene(scene: PageScene, fields: dict) -> None:
    scene.beat = str(fields.get("beat") or "")
    scene.duration = _duration_value(fields.get("duration")) or scene.duration
    scene.lines = _line_list(fields.get("lines"))


# Read the clip length the model asked for, or 0 when it gave none.
def _duration_value(value: object) -> int:
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


# Estimate the clip length, refusing pages that no single clip can hold.
def _finish_scene(scene: PageScene) -> PageScene:
    if scene.error:
        return scene

    seconds = _estimate_duration(scene.lines)
    if seconds > MAX_DURATION:
        scene.error = f"needs {seconds}s, over the {MAX_DURATION}s limit"
        return scene

    # The lines set a floor; the model may ask for more room to act.
    scene.duration = min(
        MAX_DURATION, max(MIN_DURATION, seconds + 1, scene.duration)
    )
    return scene


# Estimate how many seconds of speech these lines need.
def _estimate_duration(lines: list[Line]) -> int:
    return max(1, ceil(_speech_seconds(lines)))


# Estimate how long these lines take to read aloud, mixed languages included.
def _speech_seconds(lines: list[Line]) -> float:
    chinese = 0
    english = 0
    for line in lines:
        for char in line.text:
            if not char.isascii():
                chinese += 1
            elif char.isalnum():
                english += 1
    return chinese / _CHINESE_PER_SECOND + english / _ENGLISH_PER_SECOND


# Keep only what the model produced, so the cache holds no page identity.
def _scene_fields(scene: PageScene) -> dict:
    return {
        "beat": scene.beat,
        "duration": scene.duration,
        "lines": [line.to_dict() for line in scene.lines],
    }


def save_screenplay(
    screenplay: Screenplay,
    root: str | Path | None = None,
) -> Path:
    """Write the screenplay to <root>/<id>/screenplay.json."""
    return write_json(screenplay.id, "screenplay", screenplay.to_dict(), root)
