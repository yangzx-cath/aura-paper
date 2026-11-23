"""Render a PDF into logical pages and write ingest.json."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from PIL import Image

from ..clients.llm import LLMClient, LLMError
from ..clients.reply import extract_json
from ..media.image import (
    crop_box,
    load_image,
    save_jpeg,
    stitch_side_by_side,
    thumbnail,
)
from ..media.pdf import (
    DEFAULT_DPI,
    DEFAULT_QUALITY,
    RenderedPage,
    render_pdf,
)
from ..prompts import layout_prompt
from ..schema.book import Book, Page
from ..store.cache import Cache, file_fingerprint, fingerprint
from ..store.output import write_json
from .paths import book_dir

# A spread is about twice as wide as one page.
SPREAD_RATIO = 1.6

# The copy sent with the layout question fits in this box.
THUMBNAIL_BOX = (1024, 1024)
THUMBNAIL_QUALITY = 85

# The two halves of a spread are cut at the middle.
SPLIT_POINT = 500

# A box covers the whole image.
FULL_BOX = [[0, 0, 1000, 1000]]

# The cover stands alone, so pairing starts after it.
COVER_PAGES = 1

# Facing pages may share this share of the page width at the fold.
SEAM_SHARE = 0.08

# Page files are numbered by their order in the book.
PAGE_TEMPLATE = "p{index:03d}.jpg"


def ingest(
    pdf_path: str | Path,
    book_id: str,
    *,
    llm: LLMClient,
    root: str | Path | None = None,
    dpi: int = DEFAULT_DPI,
    quality: int = DEFAULT_QUALITY,
    pair_from: int = COVER_PAGES,
    cache: Cache | None = None,
    on_page: Callable[[Page], None] | None = None,
) -> Book:
    """Render a PDF into logical pages and write <root>/<id>/ingest.json."""
    directory = book_dir(book_id, root)
    source_dir = directory / "source"
    pages_dir = directory / "pages"
    _empty(source_dir)
    _empty(pages_dir)

    rendered = render_pdf(pdf_path, source_dir, dpi=dpi, quality=quality)
    book = Book(
        id=book_id,
        source=str(Path(pdf_path).expanduser()),
        dpi=dpi,
        pair_from=pair_from,
        source_count=len(rendered),
    )
    if not rendered:
        book.error = "the pdf has no pages"
        return book

    ns = f"ingest/{book_id}"
    groups = _page_groups(rendered, pair_from)
    index = 0
    for group in groups:
        pages = _build_pages(
            group,
            index,
            source_dir,
            pages_dir,
            llm,
            cache,
            ns,
            quality,
        )
        book.pages.extend(pages)
        index += len(pages)
        if on_page is not None:
            for page in pages:
                on_page(page)

    write_json(book_id, "ingest", book.to_dict(), root)
    return book


# Remove files left by an earlier run, so the folders match this one.
def _empty(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for entry in folder.iterdir():
        if entry.is_file():
            entry.unlink()


# Group the pages into the images the layout question looks at.
def _page_groups(
    pages: list[RenderedPage],
    pair_from: int,
) -> list[list[RenderedPage]]:
    result = []
    index = 0
    while index < len(pages):
        page = pages[index]
        if index < pair_from or _is_spread(page):
            result.append([page])
            index += 1
            continue

        following = None
        if index + 1 < len(pages):
            following = pages[index + 1]
        if following is not None and not _is_spread(following):
            result.append([page, following])
            index += 2
        else:
            result.append([page])
            index += 1
    return result


# Tell whether one page is already as wide as two printed pages.
def _is_spread(page: RenderedPage) -> bool:
    return page.width >= page.height * SPREAD_RATIO


# Turn one group of one or two PDF pages into logical pages.
def _build_pages(
    group: list[RenderedPage],
    start: int,
    source_dir: Path,
    pages_dir: Path,
    llm: LLMClient,
    cache: Cache | None,
    ns: str,
    quality: int,
) -> list[Page]:
    image, wide = _group_image(group, source_dir)
    sources = [page.index for page in group]
    text = "\n".join(page.text for page in group if page.text)

    two_pages = False
    error = ""
    # A stitched pair is one picture by construction, so only a single
    # page that is already wide can still hold two printed pages.
    if len(group) == 1 and wide:
        two_pages, error = _ask_layout(image, llm, cache, ns, start)

    if not two_pages:
        origin = "spread" if len(group) == 2 or wide else "page"
        page = _page(start, sources, FULL_BOX, origin, text, error)
        written = _write(image, page, pages_dir, quality)
        return [written]

    left_box = (0, 0, SPLIT_POINT, 1000)
    right_box = (SPLIT_POINT, 0, 1000, 1000)
    left_half = crop_box(image, left_box)
    right_half = crop_box(image, right_box)

    first_page = _page(start, sources, [list(left_box)], "half", text, error)
    second_page = _page(
        start + 1, sources, [list(right_box)], "half", text, error
    )

    first = _write(left_half, first_page, pages_dir, quality)
    second = _write(right_half, second_page, pages_dir, quality)
    return [first, second]


# Build one group image and say whether it is wide enough for two pages.
def _group_image(
    group: list[RenderedPage],
    source_dir: Path,
) -> tuple[Image.Image, bool]:
    if len(group) == 1:
        image = load_image(source_dir / group[0].filename)
    else:
        left = source_dir / group[0].filename
        right = source_dir / group[1].filename
        limit = round(group[0].width * SEAM_SHARE)
        image = stitch_side_by_side(left, right, limit)
    wide = image.width >= image.height * SPREAD_RATIO
    return image, wide


# Ask the model whether one wide page holds two printed pages. Errors keep
# it whole.
def _ask_layout(
    image: Image.Image,
    llm: LLMClient,
    cache: Cache | None,
    ns: str,
    start: int,
) -> tuple[bool, str]:
    prompt = layout_prompt()
    name = f"group{start:03d}"

    with tempfile.TemporaryDirectory() as folder:
        copy = thumbnail(image, THUMBNAIL_BOX)
        path = Path(folder) / "layout.jpg"
        save_jpeg(copy, path, THUMBNAIL_QUALITY)

        key = ""
        if cache is not None:
            digest = file_fingerprint(path)
            key = fingerprint(digest, prompt, *llm.signature)
            entry = cache.load_json(ns, name, key)
            if entry is not None:
                return _as_bool(entry.get("two_pages")), ""

        try:
            reply = llm.chat(prompt, images=[path])
            fields = extract_json(reply)
        except (LLMError, ValueError) as exc:
            return False, str(exc)

    two_pages = _as_bool(fields.get("two_pages"))
    if cache is not None:
        cache.save_json(ns, name, key, {"two_pages": two_pages})
    return two_pages, ""


# The model may answer with true, "true" or 1, so read all of them.
def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


# Build one page record with zero width and height.
def _page(
    index: int,
    sources: list[int],
    boxes: list[list[int]],
    origin: str,
    text: str,
    error: str,
) -> Page:
    return Page(
        index=index,
        filename=PAGE_TEMPLATE.format(index=index),
        width=0,
        height=0,
        sources=sources,
        boxes=boxes,
        origin=origin,
        text=text,
        error=error,
    )


# Write one page image and record its size.
def _write(
    image: Image.Image,
    page: Page,
    pages_dir: Path,
    quality: int,
) -> Page:
    width, height = save_jpeg(image, pages_dir / page.filename, quality)
    page.width = width
    page.height = height
    return page
