"""Pick the cast and place reference images."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from ..clients.llm import LLMClient, LLMError
from ..clients.reply import extract_json
from ..media.image import crop_box, load_image, save_jpeg
from ..prompts import cast_prompt, location_prompt
from ..schema.cast import BookCast, FigurePick
from ..schema.content import BookContent, Figure, PageContent
from ..schema.location import BookLocations
from ..store.cache import Cache, file_fingerprint, fingerprint
from ..store.output import write_json
from .paths import (
    book_dir,
    figure_name,
    figures_dir,
    panel_name,
    panels_dir,
)

# A crop below this share of the page is too small to show a character.
MIN_AREA = 0.05

# A crop sharing more than this share with a neighbor cannot stand alone.
MAX_OVERLAP = 0.3

# Faces first, then profiles, then side views.
FACING_RANK = {"正面": 3, "斜侧": 2, "侧面": 1}

# Crops come from an already encoded page, so keep the second encode clean.
FIGURE_QUALITY = 95

# Keep a second crop per character, in case the best one is a poor crop.
MAX_PICTURES = 2


def pick_figures(
    book_id: str,
    *,
    root: str | Path | None = None,
) -> list[FigurePick]:
    """Crop every usable figure to the figures folder, best first."""
    directory = book_dir(book_id, root)
    pages_dir = directory / "pages"
    out_dir = figures_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)

    picks = []
    for page in _read_content(directory).pages:
        chosen = [figure for figure in page.figures if _usable(page, figure)]
        if not chosen:
            continue
        image = load_image(pages_dir / page.filename)
        for figure in chosen:
            picks.append(_save(image, page, figure, out_dir))

    picks.sort(key=_rank, reverse=True)
    return picks


def assets(
    book_id: str,
    *,
    llm: LLMClient,
    root: str | Path | None = None,
    cache: Cache | None = None,
) -> tuple[BookCast, BookLocations]:
    """Read understand.json, build the reference images, write two files."""
    directory = book_dir(book_id, root)
    pages = _read_content(directory).pages
    picks = pick_figures(book_id, root=root)
    cast_book = BookCast(id=book_id, model=llm.model)
    places = BookLocations(id=book_id, model=llm.model)
    if picks:
        _fill(cast_book, llm, pages, picks, cache, book_id, root)
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
    picks: list[FigurePick],
    cache: Cache | None,
    book_id: str,
    root: str | Path | None,
) -> None:
    prompt = cast_prompt(pages, picks)
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
    picks: list[FigurePick],
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


# Tell whether a figure can stand alone as a reference image.
def _usable(page: PageContent, figure: Figure) -> bool:
    box = figure.box
    if box is None:
        return False
    if figure.view != "全身" or figure.occlusion != "无":
        return False
    if figure.facing not in FACING_RANK:
        return False
    if _area(box) < MIN_AREA:
        return False
    return _worst_overlap(page, figure, box) <= MAX_OVERLAP


# Cut one figure out of its page and keep the record of it.
def _save(
    image: Image.Image,
    page: PageContent,
    figure: Figure,
    out_dir: Path,
) -> FigurePick:
    box = figure.box
    assert box is not None
    left, top, right, bottom = box
    name = figure_name(page.filename, figure.index)
    crop = crop_box(image, (left, top, right, bottom))
    save_jpeg(crop, out_dir / name, FIGURE_QUALITY)
    return FigurePick(
        page=page.filename,
        figure=figure.index,
        file=name,
        facing=figure.facing,
        area=_area(box),
    )


# Return the share of the page a per-mille box covers.
def _area(box: list[int]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1]) / 1_000_000


# Return the share of the smaller box that two boxes have in common.
def _overlap(first: list[int], second: list[int]) -> float:
    width = min(first[2], second[2]) - max(first[0], second[0])
    height = min(first[3], second[3]) - max(first[1], second[1])
    if width <= 0 or height <= 0:
        return 0.0
    shared = width * height / 1_000_000
    return shared / min(_area(first), _area(second))


# Return the largest share this figure box shares with another on the page.
def _worst_overlap(
    page: PageContent,
    figure: Figure,
    box: list[int],
) -> float:
    overlaps = []
    for other in page.figures:
        if other is figure or other.box is None:
            continue
        overlaps.append(_overlap(box, other.box))
    return max(overlaps, default=0.0)


# Sort key: faces before profiles, then the larger crop.
def _rank(pick: FigurePick) -> tuple[int, float]:
    return (FACING_RANK[pick.facing], pick.area)


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
