"""Publish a finished book into the library the reader loads it from."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..schema.cast import BookCast
from ..schema.compose import BookCompose
from ..schema.content import BookContent, language_of
from ..schema.publish import BookPublish, PublishCast, PublishPage
from ..schema.subtitles import BookSubtitles
from ..store.books import PUB_NAME, book_folder, read_meta, write_publish
from ..store.output import write_json
from .paths import book_dir

# The names the release uses inside pub/, so a reader link never changes.
FILM_NAME = "film.mp4"
VTT_NAME = "subtitles.vtt"
COVER_NAME = "cover.jpg"


def publish(
    book_id: str,
    *,
    as_id: str = "",
    root: str | Path | None = None,
    library: str | Path | None = None,
) -> BookPublish:
    """Copy the film, its subtitles and the book facts into the library."""
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

    target = book_folder(target_id, library) / PUB_NAME
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(film, target / FILM_NAME)
    shutil.copyfile(subtitles, target / VTT_NAME)

    cover = directory / COVER_NAME
    if cover.is_file():
        shutil.copyfile(cover, target / COVER_NAME)
        result.cover = COVER_NAME

    content = _read_content(directory)
    cast_book = _read_cast(directory)
    meta = read_meta(target_id, library)
    result.title = content.title or (meta.title if meta is not None else "")
    result.language = cast_book.language or _content_language(content)
    result.seconds = takes.seconds
    result.cues = _read_subtitles(directory).cues
    result.film = FILM_NAME
    result.vtt = VTT_NAME
    result.cast = [
        PublishCast(id=member.id, name=member.name)
        for member in cast_book.cast
        if member.id
    ]
    result.pages = _pages(content, directory)
    # The studio reads the run from the out folder, the reader from the
    # library, so the manifest goes to both.
    write_json(book_id, "publish", result.to_dict(), root)
    write_publish(target_id, result.to_dict(), library)
    return result


# Draw the page table the reader searches: when a page plays, what it says.
def _pages(content: BookContent, directory: Path) -> list[PublishPage]:
    spans = _spans(directory)
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
            )
        )
    return pages


# When each page plays: a shot covers its pages from its own start.
def _spans(directory: Path) -> dict[int, tuple[float, float]]:
    shots = _read_json(directory / "shots.json").get("shots") or []
    takes = {take.shot: take for take in _read_compose(directory).shots}
    spans: dict[int, tuple[float, float]] = {}
    for shot in shots:
        take = takes.get(str(shot.get("id") or ""))
        if take is None:
            continue
        start = take.start
        end = start + take.seconds
        for panel in shot.get("panels") or []:
            number = _page_number(panel.get("page"))
            if number is None:
                continue
            low, high = spans.get(number, (start, end))
            spans[number] = (min(low, start), max(high, end))
    return spans


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
