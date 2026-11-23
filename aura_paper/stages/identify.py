"""Name the people in the panels that show a character only in part."""

from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from ..cache import Cache, file_fingerprint, fingerprint
from ..clients.llm import LLMClient, LLMError
from ..media.image import load_image, save_jpeg, thumbnail
from ..output import write_json
from ..prompts import identify_prompt
from ..schema.cast import BookCast
from ..schema.content import BookContent, Figure, PageContent
from ..schema.identify import BookPeople, PanelPeople
from ..utils import extract_json
from .paths import (
    book_dir,
    identify_dir,
    panel_name,
)

# Small parts must stay readable, so these copies are bigger than the plan's.
READ_BOX = (768, 768)
READ_QUALITY = 90
FIGURE_QUALITY = 95


def identify(
    book_id: str,
    *,
    llm: LLMClient,
    only: str = "",
    workers: int = 1,
    root: str | Path | None = None,
    cache: Cache | None = None,
    on_page: Callable[[PageContent, int, float], None] | None = None,
) -> BookPeople:
    """Read understand.json, name the people of every partly shown figure."""
    assert workers >= 1

    directory = book_dir(book_id, root)
    pages = _read_content(directory).pages
    cast_book = _read_cast(directory)
    result = BookPeople(id=book_id, model=llm.model)

    wanted = [page for page in pages if _cut(page)]
    if only:
        wanted = [page for page in wanted if _stem(page) == only]
    if not wanted:
        write_json(book_id, "identify", result.to_dict(), root)
        return result

    out_dir = identify_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    def run(page: PageContent) -> tuple[PageContent, list[PanelPeople], str]:
        started = time.perf_counter()
        found: list[PanelPeople] = []
        error = ""
        try:
            found = _one_page(
                page,
                cast_book,
                directory,
                out_dir,
                llm,
                cache,
                book_id,
            )
        except (LLMError, ValueError) as exc:
            error = str(exc)
        if on_page is not None:
            on_page(page, len(found), time.perf_counter() - started)
        return page, found, error

    if workers == 1:
        done = [run(page) for page in wanted]
    else:
        # pool.map() keeps the input order, so pages stay in book order.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            done = list(pool.map(run, wanted))

    for page, found, error in done:
        result.panels.extend(found)
        if error:
            result.error = _joined(result.error, f"{page.filename}：{error}")

    write_json(book_id, "identify", result.to_dict(), root)
    return result


# Tell whether a page shows a character that is cut off or never cropped.
def _cut(page: PageContent) -> bool:
    return any(_partly(figure) for figure in page.figures)


# Tell whether one figure is shown only in part.
def _partly(figure: Figure) -> bool:
    return (
        figure.view != "全身" or figure.occlusion != "无" or figure.box is None
    )


# Name the people of every panel on one page.
def _one_page(
    page: PageContent,
    cast_book: BookCast,
    directory: Path,
    out_dir: Path,
    llm: LLMClient,
    cache: Cache | None,
    book_id: str,
) -> list[PanelPeople]:
    panels = [
        panel.index
        for panel in page.panels
        if (
            directory / "panels" / panel_name(page.filename, panel.index)
        ).is_file()
    ]
    refs = _refs(cast_book, directory)
    if not panels:
        return []

    prompt = identify_prompt(
        page.page_text,
        cast_book,
        panels,
        {
            cast_id: len(panels) + number
            for number, cast_id in enumerate(refs, start=1)
        },
    )
    images = _read_copies(page, panels, refs, directory, out_dir)
    fields = _ask(llm, prompt, images, cache, book_id, _stem(page))
    return _apply(fields, page, cast_book, panels)


# Pick the image that stands for each character.
def _refs(cast_book: BookCast, directory: Path) -> dict[str, Path]:
    refs = {}
    for member in cast_book.cast:
        for name in member.pictures:
            path = directory / "figures" / name
            if path.is_file():
                refs[member.id] = path
                break
    return refs


# Shrink the panels and the references to the size the model reads.
def _read_copies(
    page: PageContent,
    panels: list[int],
    refs: dict[str, Path],
    directory: Path,
    out_dir: Path,
) -> list[Path]:
    stem = _stem(page)
    kept = []
    for index in panels:
        source = directory / "panels" / panel_name(page.filename, index)
        target = out_dir / f"{stem}-{index}.jpg"
        save_jpeg(
            thumbnail(load_image(source), READ_BOX), target, READ_QUALITY
        )
        kept.append(target)
    for cast_id, source in refs.items():
        target = out_dir / f"{stem}-{cast_id}.jpg"
        save_jpeg(
            thumbnail(load_image(source), READ_BOX), target, FIGURE_QUALITY
        )
        kept.append(target)
    return kept


# Send the copies and read the reply as JSON.
def _ask(
    llm: LLMClient,
    prompt: str,
    images: list[Path],
    cache: Cache | None,
    book_id: str,
    name: str,
) -> dict:
    if cache is None:
        return extract_json(llm.chat(prompt, images=images))

    ns = f"identify/{book_id}"
    key = fingerprint(
        *[file_fingerprint(path) for path in images],
        prompt,
        *llm.signature,
    )
    entry = cache.load_json(ns, name, key)
    if entry is not None:
        return entry

    fields = extract_json(llm.chat(prompt, images=images))
    cache.save_json(ns, name, key, fields)
    return fields


# Turn the answer into the people of every panel, keeping the ids that exist.
def _apply(
    fields: dict,
    page: PageContent,
    cast_book: BookCast,
    panels: list[int],
) -> list[PanelPeople]:
    known = {member.id for member in cast_book.cast}
    wanted = set(panels)
    kept = []
    for entry in fields.get("panels") or []:
        if not isinstance(entry, dict):
            continue
        index = _int(entry.get("panel"))
        if index not in wanted:
            continue
        people = []
        for item in entry.get("people") or []:
            if not isinstance(item, dict):
                continue
            cast_id = str(item.get("cast") or "").strip()
            parts = str(item.get("parts") or "").strip()
            if cast_id in known and parts:
                people.append({"cast": cast_id, "parts": parts})
        kept.append(
            PanelPeople.from_dict(
                {
                    "page": page.filename,
                    "panel": index,
                    "people": people,
                }
            )
        )
    return kept


# Read a number, falling back to a value no panel has.
def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1


# Join two notes into the error text of the stage.
def _joined(error: str, note: str) -> str:
    return "；".join(part for part in (error, note) if part)


# Return the page name without its suffix.
def _stem(page: PageContent) -> str:
    return Path(page.filename).stem


# Read the understand stage's record of the book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    return BookContent.from_dict(json.loads(path.read_text("utf-8")))


# Read the cast stage's record of the characters.
def _read_cast(directory: Path) -> BookCast:
    path = directory / "cast.json"
    return BookCast.from_dict(json.loads(path.read_text("utf-8")))
