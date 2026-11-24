"""Publish a finished book into the library the reader loads it from."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..schema.cast import BookCast
from ..schema.compose import BookCompose
from ..schema.content import BookContent, language_of
from ..schema.publish import BookPublish, PublishCast
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
    root: str | Path | None = None,
    library: str | Path | None = None,
) -> BookPublish:
    """Copy the film, its subtitles and the book facts into the library."""
    directory = book_dir(book_id, root)
    result = BookPublish(id=book_id)

    takes = _read_compose(directory)
    film = directory / takes.film if takes.film else None
    if film is None or not film.is_file():
        result.error = "整片还没拼，先跑 run_compose.py"
        return result
    subtitles = directory / VTT_NAME
    if not subtitles.is_file():
        result.error = "还没有字幕，先跑 run_subtitles.py"
        return result

    target = book_folder(book_id, library) / PUB_NAME
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(film, target / FILM_NAME)
    shutil.copyfile(subtitles, target / VTT_NAME)

    cover = directory / COVER_NAME
    if cover.is_file():
        shutil.copyfile(cover, target / COVER_NAME)
        result.cover = COVER_NAME

    content = _read_content(directory)
    cast_book = _read_cast(directory)
    meta = read_meta(book_id, library)
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
    # The studio reads the run from the out folder, the reader from the
    # library, so the manifest goes to both.
    write_json(book_id, "publish", result.to_dict(), root)
    write_publish(book_id, result.to_dict(), library)
    return result


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
