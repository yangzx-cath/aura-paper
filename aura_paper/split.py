"""Cut images that hold two pages into one page each."""

from __future__ import annotations

import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from .book import Book, Page
from .cache import Cache, file_fingerprint, fingerprint
from .llm import LLMClient, LLMError
from .output import write_json
from .pdf import IMAGE_QUALITY
from .prompts1 import split_prompt
from .utils import IMAGE_SUFFIXES, extract_json

# Two pages side by side are about twice as wide as one page.
TWO_PAGE_RATIO = 1.6

# The copy sent with the layout question fits in this box.
THUMBNAIL_BOX = (1024, 1024)


@dataclass
class Layout:
    """Whether one image holds two pages side by side."""

    two_pages: bool = False
    reason: str = ""
    error: str = ""


@dataclass
class Split:
    """The cut pages of one book and the decisions behind them."""

    book: Book
    decisions: list[Layout] = field(default_factory=list)

    @property
    def two_page_count(self) -> int:
        """Return how many images held two pages."""
        return sum(1 for decision in self.decisions if decision.two_pages)

    @property
    def failed_count(self) -> int:
        """Return how many images the model could not classify."""
        return sum(1 for decision in self.decisions if decision.error)


def detect_layout(
    page: Page,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    ns: str = "split",
    directory: str = "",
    base_width: int = 0,
) -> Layout:
    """Decide whether one image holds two pages side by side."""
    if not _is_candidate(page, base_width):
        return Layout()

    path = Path(directory) / page.filename
    prompt = split_prompt()

    if cache is None:
        return _ask_layout(client, prompt, path)

    key = fingerprint(
        file_fingerprint(path),
        prompt,
        *client.signature,
    )

    name = Path(page.filename).stem
    entry = cache.load_json(ns, name, key)
    if entry is not None:
        return Layout(
            two_pages=_as_bool(entry.get("two_pages")),
            reason=str(entry.get("reason") or ""),
        )

    result = _ask_layout(client, prompt, path)
    # Errors are never cached, so a failed image is retried next run.
    if not result.error:
        cache.save_json(ns, name, key, _layout_fields(result))
    return result


# Only an image about twice as wide as one page can hold two pages.
def _is_candidate(page: Page, base_width: int) -> bool:
    wide = base_width > 0 and page.width >= base_width * TWO_PAGE_RATIO
    flat = page.height > 0 and page.width >= page.height * TWO_PAGE_RATIO
    return wide or flat


# Ask the model with a downscaled copy of the image.
def _ask_layout(client: LLMClient, prompt: str, path: Path) -> Layout:
    try:
        with tempfile.TemporaryDirectory() as folder:
            thumb = _thumbnail(path, Path(folder))
            reply = client.chat(prompt, image_path=thumb)
        fields = extract_json(reply)
    except (LLMError, ValueError, OSError) as exc:
        return Layout(error=str(exc))

    return Layout(
        two_pages=_as_bool(fields.get("two_pages")),
        reason=str(fields.get("reason") or ""),
    )


# Shrink one image, keeping its shape so the gutter still shows.
def _thumbnail(path: Path, folder: Path) -> Path:
    target = folder / path.name
    with Image.open(path) as image:
        copy = image.convert("RGB")
        copy.thumbnail(THUMBNAIL_BOX, Image.Resampling.LANCZOS)
        copy.save(target, "JPEG", quality=IMAGE_QUALITY)
    return target


# The model may answer with true, "true" or 1, so read all of them.
def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _layout_fields(layout: Layout) -> dict:
    return {"two_pages": layout.two_pages, "reason": layout.reason}


def split_book(
    book: Book,
    client: LLMClient,
    *,
    target: str | Path,
    cache: Cache | None = None,
    workers: int = 1,
    on_page: Callable[[Page, Layout, float], None] | None = None,
) -> Split:
    """Cut every image that holds two pages into the target folder."""
    assert workers >= 1

    ns = f"split/{book.id}"
    base = _base_width(book.pages)
    source = Path(book.directory)
    folder = Path(target)
    folder.mkdir(parents=True, exist_ok=True)
    # The page set is rebuilt every run, so old halves cannot linger.
    _clear_images(folder)

    def run(page: Page) -> tuple[Page, Layout, float]:
        started = time.perf_counter()
        layout = detect_layout(
            page,
            client,
            cache=cache,
            ns=ns,
            directory=book.directory,
            base_width=base,
        )
        return page, layout, time.perf_counter() - started

    if workers == 1:
        results = [run(page) for page in book.pages]
    else:
        # pool.map() keeps the input order, so pages stay in book order.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, book.pages))

    split = Split(
        book=Book(
            id=book.id,
            source=book.source,
            directory=str(folder),
            dpi=book.dpi,
            title=book.title,
        )
    )
    for page, layout, elapsed in results:
        split.decisions.append(layout)
        # An image adds one page or two, so numbering continues from here.
        start_index = len(split.book.pages)
        split.book.pages.extend(
            _cut(page, layout, source, folder, start_index)
        )
        if on_page is not None:
            on_page(page, layout, elapsed)
    return split


# The narrowest image holds one page, so two pages are twice as wide.
def _base_width(pages: list[Page]) -> int:
    widths = [page.width for page in pages if page.width]
    return min(widths) if widths else 0


# Remove images left by an earlier run, so the folder matches the page list.
def _clear_images(folder: Path) -> None:
    for entry in folder.iterdir():
        if entry.is_file() and entry.suffix.lower() in IMAGE_SUFFIXES:
            entry.unlink()


# Cut one image down the middle, or copy it whole when it holds one page.
def _cut(
    page: Page,
    layout: Layout,
    source: Path,
    target: Path,
    start_index: int,
) -> list[Page]:
    if not layout.two_pages:
        shutil.copyfile(source / page.filename, target / page.filename)
        return [
            Page(
                index=start_index,
                filename=page.filename,
                width=page.width,
                height=page.height,
                text=page.text,
            )
        ]

    pages = []
    with Image.open(source / page.filename) as image:
        width, height = image.size
        middle = width // 2
        boxes = ((0, 0, middle, height), (middle, 0, width, height))
        for offset, box in enumerate(boxes):
            name = f"{Path(page.filename).stem}{'ab'[offset]}.jpg"
            piece = image.convert("RGB").crop(box)
            piece.save(target / name, "JPEG", quality=IMAGE_QUALITY)
            # The text layer covers the whole image, not one half of it.
            pages.append(
                Page(
                    index=start_index + offset,
                    filename=name,
                    width=piece.width,
                    height=piece.height,
                )
            )
    return pages


def save_split(
    split: Split,
    root: str | Path | None = None,
) -> Path:
    """Write the page list to <root>/<book_id>/pages.json."""
    return write_json(split.book.id, "pages", split.book.to_dict(), root)
