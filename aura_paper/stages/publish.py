"""Publish a finished book into the library the reader loads it from."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from ..clients.llm import LLMClient
from ..clients.reply import extract_json
from ..prompts import topic_prompt
from ..schema.cast import BookCast
from ..schema.compose import BookCompose
from ..schema.content import BookContent, language_of
from ..schema.publish import (
    BookPublish,
    PublishCast,
    PublishPage,
    PublishShot,
    PublishTopic,
)
from ..schema.scene import BookScenes
from ..schema.subtitles import BookSubtitles
from ..store.books import PUB_NAME, book_folder, read_meta, write_publish
from ..store.cache import Cache, fingerprint
from ..store.output import write_json
from .paths import book_dir

# The names the release uses inside pub/, so a reader link never changes.
FILM_NAME = "film.mp4"
VTT_NAME = "subtitles.vtt"
COVER_NAME = "cover.jpg"

# Cache namespace for the topics the model names for one book.
TOPIC_NS = "publish"

# The only kinds a topic may carry.
KINDS = ("角色", "道具", "场景", "知识点")


def publish(
    book_id: str,
    *,
    as_id: str = "",
    root: str | Path | None = None,
    library: str | Path | None = None,
    llm: LLMClient | None = None,
    cache: Cache | None = None,
) -> BookPublish:
    """Copy the film, subtitles and tappable topics into the library."""
    directory = book_dir(book_id, root)
    target_id = as_id or book_id
    result = BookPublish(id=target_id)

    takes = _read_compose(directory)
    film = directory / takes.film if takes.film else None
    if film is None or not film.is_file():
        result.error = "整片还没拼，先跑 run_compose.py"
        return result
    subtitles = directory / VTT_NAME
    if not subtitles.is_file():
        result.error = "还没有字幕，先跑 run_subtitles.py"
        return result

    content = _read_content(directory)
    cast_book = _read_cast(directory)
    meta = read_meta(target_id, library)
    result.title = content.title or (meta.title if meta is not None else "")
    result.language = cast_book.language or _content_language(content)
    result.seconds = takes.seconds
    result.cues = _read_subtitles(directory).cues
    result.shots = _shots(directory)
    result.pages = _pages(content, result.shots)
    # The topics cost a model call, so they are settled before any copy:
    # a failed call leaves the previous release untouched.
    result.topics = _topics(
        target_id, result.title, cast_book, result.pages, llm, cache
    )

    target = book_folder(target_id, library) / PUB_NAME
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(film, target / FILM_NAME)
    shutil.copyfile(subtitles, target / VTT_NAME)

    cover = directory / COVER_NAME
    if cover.is_file():
        shutil.copyfile(cover, target / COVER_NAME)
        result.cover = COVER_NAME

    result.film = FILM_NAME
    result.vtt = VTT_NAME
    result.cast = [
        PublishCast(id=member.id, name=member.name)
        for member in cast_book.cast
        if member.id
    ]
    # The studio reads the run from the out folder, the reader from the
    # library, so the manifest goes to both.
    write_json(book_id, "publish", result.to_dict(), root)
    write_publish(target_id, result.to_dict(), library)
    return result


# Draw the page table the reader searches: when a page plays, what it says.
def _pages(
    content: BookContent,
    shots: list[PublishShot],
) -> list[PublishPage]:
    spans: dict[int, tuple[float, float]] = {}
    owners: dict[int, list[str]] = {}
    for shot in shots:
        for number in shot.pages:
            low, high = spans.get(number, (shot.start, shot.end))
            spans[number] = (min(low, shot.start), max(high, shot.end))
            owners.setdefault(number, []).append(shot.id)

    pages = []
    for index, page in enumerate(content.pages):
        start, end = spans.get(index, (0.0, 0.0))
        said = [panel.text for panel in page.panels if panel.text]
        drawn = [panel.description for panel in page.panels]
        names = [figure.name for figure in page.figures if figure.name]
        pages.append(
            PublishPage(
                page=index,
                start=start,
                end=end,
                text="\n".join(said),
                desc=" ".join(drawn),
                cast=names,
                shots=owners.get(index, []),
            )
        )
    return pages


# When each shot plays and which pages it shows, so a time maps back to it.
def _shots(directory: Path) -> list[PublishShot]:
    rows = _read_json(directory / "shots.json").get("shots") or []
    takes = {take.shot: take for take in _read_compose(directory).shots}
    names = {scene.id: scene.name for scene in _read_scenes(directory).scenes}
    shots = []
    for row in rows:
        shot_id = str(row.get("id") or "")
        take = takes.get(shot_id)
        if take is None:
            continue
        scene = str(row.get("scene") or "")
        pages = sorted(
            {
                number
                for number in (
                    _page_number(panel.get("page"))
                    for panel in row.get("panels") or []
                )
                if number is not None
            }
        )
        shots.append(
            PublishShot(
                id=shot_id,
                scene=scene,
                scene_name=names.get(scene, ""),
                start=take.start,
                end=take.start + take.seconds,
                pages=pages,
            )
        )
    return shots


# Ask the model which things are worth tapping, reusing an earlier answer.
def _topics(
    book_id: str,
    title: str,
    cast_book: BookCast,
    pages: list[PublishPage],
    llm: LLMClient | None,
    cache: Cache | None,
) -> list[PublishTopic]:
    if llm is None or not pages:
        return []

    prompt = topic_prompt(title, cast_book, pages)
    story = "\n".join(f"{page.page}:{page.text}{page.desc}" for page in pages)
    key = fingerprint(story, prompt, *llm.signature)

    entry = None
    if cache is not None:
        entry = cache.load_json(TOPIC_NS, book_id, key)
    if entry is None:
        entry = extract_json(llm.chat(prompt))
        if cache is not None:
            cache.save_json(TOPIC_NS, book_id, key, entry)
    return _read_topics(entry, len(pages))


# Keep the topics the model wrote, dropping the ones it left incomplete.
def _read_topics(fields: dict, page_count: int) -> list[PublishTopic]:
    rows = fields.get("topics")
    if not isinstance(rows, list):
        return []

    topics = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _clean_text(str(row.get("name") or ""))
        intro = _clean_text(str(row.get("intro") or ""))
        pages = _page_numbers(row.get("pages"), page_count)
        if not name or not intro or not pages:
            continue
        topics.append(
            PublishTopic(
                id=f"t{len(topics) + 1}",
                name=name,
                kind=_kind(row.get("kind")),
                aliases=_aliases(row.get("aliases"), name),
                visual=_clean_text(str(row.get("visual") or "")),
                intro=intro,
                pages=pages,
            )
        )
    return topics


# Fold the whitespace the model picked up from line breaks in the page text.
def _clean_text(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", flat)


# Keep the kind only when the model used one of the four words.
def _kind(value: object) -> str:
    text = str(value or "").strip()
    return text if text in KINDS else ""


# Keep the other names for a topic, without repeating its own name.
def _aliases(value: object, name: str) -> list[str]:
    if not isinstance(value, list):
        return []
    words = []
    for item in value:
        text = str(item or "").strip()
        if text and text != name and text not in words:
            words.append(text)
    return words


# Keep the page numbers a topic claims, ignoring anything out of range.
def _page_numbers(value: object, page_count: int) -> list[int]:
    if not isinstance(value, list):
        return []
    numbers = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        if 0 <= item < page_count:
            numbers.add(item)
    return sorted(numbers)


# p002.jpg is page 2, counted from the cover at p000.jpg.
def _page_number(name: object) -> int | None:
    stem = Path(str(name or "")).stem
    if len(stem) < 2 or stem[0] != "p" or not stem[1:].isdigit():
        return None
    return int(stem[1:])


# Read one JSON file, treating a missing or broken file as empty.
def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# Read the record of the finished film, or an empty one this stage waits on.
def _read_compose(directory: Path) -> BookCompose:
    path = directory / "compose.json"
    if not path.is_file():
        return BookCompose()
    return BookCompose.from_dict(json.loads(path.read_text("utf-8")))


# Read what the pages say about the book, or an empty book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    if not path.is_file():
        return BookContent(id="", source="")
    return BookContent.from_dict(json.loads(path.read_text("utf-8")))


# Read the cast, or an empty one when the book has none.
def _read_cast(directory: Path) -> BookCast:
    path = directory / "cast.json"
    if not path.is_file():
        return BookCast()
    return BookCast.from_dict(json.loads(path.read_text("utf-8")))


# Read the scene names, or an empty set when the book has none.
def _read_scenes(directory: Path) -> BookScenes:
    path = directory / "scenes.json"
    if not path.is_file():
        return BookScenes()
    return BookScenes.from_dict(json.loads(path.read_text("utf-8")))


# Read how many cues the subtitle file holds.
def _read_subtitles(directory: Path) -> BookSubtitles:
    path = directory / "subtitles.json"
    if not path.is_file():
        return BookSubtitles()
    return BookSubtitles.from_dict(json.loads(path.read_text("utf-8")))


# Name the language from the words on the pages, when the cast is silent.
def _content_language(content: BookContent) -> str:
    words = "".join(page.page_text for page in content.pages)
    return language_of(words)
