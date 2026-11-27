"""Read the cast of a book and the places it happens in."""

from __future__ import annotations

import json
from pathlib import Path

from ..clients.llm import LLMClient, LLMError
from ..clients.reply import extract_json
from ..prompts import cast_prompt, location_prompt
from ..schema.cast import BookCast
from ..schema.content import BookContent, PageContent
from ..schema.crop import BookCrop, FigureCrop
from ..schema.location import BookLocations
from ..store.cache import Cache, file_fingerprint, fingerprint
from ..store.output import write_json
from .paths import book_dir, figures_dir, panel_name, panels_dir

# Keep a second crop per character, in case the best one is a poor crop.
MAX_PICTURES = 2


def assets(
    book_id: str,
    *,
    llm: LLMClient,
    root: str | Path | None = None,
    cache: Cache | None = None,
) -> tuple[BookCast, BookLocations]:
    """Read understand.json, build the reference images, write two files."""
    directory = book_dir(book_id, root)
    content = _read_content(directory)
    pages = content.pages
    picks = _read_figures(directory)
    cast_book = BookCast(
        id=book_id,
        language=content.language,
        model=llm.model,
    )
    places = BookLocations(id=book_id, model=llm.model)
    if picks:
        _fill(
            cast_book,
            llm,
            pages,
            picks,
            content.language,
            cache,
            book_id,
            root,
        )
    full = _full_panels(pages)
    if full:
        _fill_locations(places, llm, pages, full, cache, book_id, root)
    write_json(book_id, "cast", cast_book.to_dict(), root)
    write_json(book_id, "locations", places.to_dict(), root)
    return cast_book, places


# Ask the model which crops show the same character, then fill the result.
def _fill(
    result: BookCast,
    llm: LLMClient,
    pages: list[PageContent],
    picks: list[FigureCrop],
    language: str,
    cache: Cache | None,
    book_id: str,
    root: str | Path | None,
) -> None:
    prompt = cast_prompt(pages, picks, language=language)
    images = [figures_dir(book_id, root) / pick.file for pick in picks]
    try:
        fields = _ask(llm, prompt, images, cache, book_id, "cast")
    except (LLMError, ValueError) as exc:
        result.error = _joined(result.error, str(exc))
        return
    _apply(result, fields, picks)
    if not result.cast:
        result.error = "model returned no cast"


# Return the panels that already show a whole environment.
def _full_panels(pages: list[PageContent]) -> list[tuple[str, int, str]]:
    full = []
    for page in pages:
        for panel in page.panels:
            if panel.needs_scene or panel.box is None:
                continue
            crop = panel_name(page.filename, panel.index)
            full.append((page.filename, panel.index, crop))
    return full


# Ask the model which panels share a place, then fill the result.
def _fill_locations(
    result: BookLocations,
    llm: LLMClient,
    pages: list[PageContent],
    full: list[tuple[str, int, str]],
    cache: Cache | None,
    book_id: str,
    root: str | Path | None,
) -> None:
    prompt = location_prompt(pages, full)
    images = [panels_dir(book_id, root) / crop for _, _, crop in full]
    try:
        fields = _ask(llm, prompt, images, cache, book_id, "locations")
    except (LLMError, ValueError) as exc:
        result.error = _joined(result.error, str(exc))
        return
    _apply_locations(result, fields, pages, full)
    if not result.locations:
        result.error = _joined(result.error, "model returned no location")
    if not result.style:
        result.error = _joined(result.error, "model returned no style")


# Turn the place answer into locations and a place for every panel.
def _apply_locations(
    result: BookLocations,
    fields: dict,
    pages: list[PageContent],
    full: list[tuple[str, int, str]],
) -> None:
    crops = {crop for _, _, crop in full}
    entries = []
    ids: dict[str, str] = {}
    for entry in fields.get("locations") or []:
        if not isinstance(entry, dict):
            continue
        location_id = f"l{len(entries) + 1}"
        key = str(entry.get("key") or "").strip()
        if key:
            ids[key] = location_id
        master = str(entry.get("master") or "").strip()
        entries.append(
            {
                "id": location_id,
                "name": entry.get("name"),
                "light": entry.get("light"),
                "master": master if master in crops else "",
            }
        )

    owners: dict[tuple[str, int], str] = {}
    for entry in fields.get("panel_locations") or []:
        if not isinstance(entry, dict):
            continue
        page_name = str(entry.get("page") or "").strip()
        index = _int(entry.get("panel"))
        key = str(entry.get("key") or "").strip()
        owners[(page_name, index)] = ids.get(key, "")

    result.style = str(fields.get("style") or "").strip()
    parsed = BookLocations.from_dict(
        {
            "locations": entries,
            "panel_locations": [
                {
                    "page": page.filename,
                    "panel": panel.index,
                    "location": owners.get((page.filename, panel.index), ""),
                }
                for page in pages
                for panel in page.panels
            ],
        }
    )
    result.locations = parsed.locations
    result.panel_locations = parsed.panel_locations


# Read the grouping answer, reusing the cached one when nothing changed.
def _ask(
    llm: LLMClient,
    prompt: str,
    images: list[Path],
    cache: Cache | None,
    book_id: str,
    name: str,
) -> dict:
    if cache is None:
        return _chat(llm, prompt, images)

    ns = f"assets/{book_id}"
    key = _key(images, prompt, llm)
    entry = cache.load_json(ns, name, key)
    if entry is not None:
        return entry

    fields = _chat(llm, prompt, images)
    cache.save_json(ns, name, key, fields)
    return fields


# Send the crops and read the reply as JSON.
def _chat(llm: LLMClient, prompt: str, images: list[Path]) -> dict:
    return extract_json(llm.chat(prompt, images=images))


# Fingerprint the crops, the prompt and the model, so the key is exact.
def _key(images: list[Path], prompt: str, llm: LLMClient) -> str:
    digests = [file_fingerprint(path) for path in images]
    return fingerprint(*digests, prompt, *llm.signature)


# Turn the answer into characters, crop owners and resolutions.
def _apply(
    result: BookCast,
    fields: dict,
    picks: list[FigureCrop],
) -> None:
    members = []
    ids: dict[str, str] = {}
    preferred: dict[str, str] = {}
    for entry in fields.get("cast") or []:
        if not isinstance(entry, dict):
            continue
        cast_id = f"c{len(members) + 1}"
        key = str(entry.get("key") or "").strip()
        if key:
            ids[key] = cast_id
            best = str(entry.get("best") or "").strip()
            if best:
                preferred[cast_id] = best
        members.append(
            {
                "id": cast_id,
                "name": entry.get("name"),
                "look": entry.get("look"),
                "voice": entry.get("voice"),
            }
        )

    owners: dict[str, str] = {}
    for entry in fields.get("figure_cast") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        owners[str(entry.get("file") or "").strip()] = ids.get(key, "")

    parsed = BookCast.from_dict(
        {
            "cast": members,
            "figure_cast": [
                {"file": pick.file, "cast": owners.get(pick.file, "")}
                for pick in picks
            ],
            "resolved": fields.get("resolved"),
            "open": fields.get("open"),
        }
    )
    result.cast = parsed.cast
    result.figure_cast = parsed.figure_cast
    result.resolved = parsed.resolved
    result.open = parsed.open

    # The model's pick wins when it is one of the crops it gave that character.
    ranked: dict[str, list[str]] = {}
    for pick in picks:
        owner = owners.get(pick.file, "")
        if owner:
            ranked.setdefault(owner, []).append(pick.file)
    for member in result.cast:
        files = ranked.get(member.id, [])
        best = preferred.get(member.id, "")
        if best in files:
            files.remove(best)
            files.insert(0, best)
        member.pictures = files[:MAX_PICTURES]


# Read the understand stage's record of the book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    text = path.read_text(encoding="utf-8")
    return BookContent.from_dict(json.loads(text))


# Read the figures the crop stage cut, best first.
def _read_figures(directory: Path) -> list[FigureCrop]:
    path = directory / "crop.json"
    text = path.read_text(encoding="utf-8")
    return BookCrop.from_dict(json.loads(text)).figures


# Read an integer, falling back to -1 when the value is unusable.
def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1


# Join two error texts into one line.
def _joined(first: str, second: str) -> str:
    if not first:
        return second
    return f"{first}；{second}"
