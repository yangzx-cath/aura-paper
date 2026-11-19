"""Cut two-page spreads into single pages before they are understood."""

from __future__ import annotations

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
from .prompts import split_prompt
from .utils import extract_json

# A spread is about twice as wide as the narrowest page of its book.
SPREAD_RATIO = 1.6

# The copy sent with the layout question fits in this box.
THUMBNAIL_BOX = (1024, 1024)


@dataclass
class Spread:
    """The spread decision of one page."""

    spread: bool = False
    reason: str = ""
    error: str = ""


@dataclass
class Split:
    """The cut pages of one book and the decisions behind them."""

    book: Book
    decisions: list[Spread] = field(default_factory=list)

    @property
    def spread_count(self) -> int:
        """Return how many pages held two pages side by side."""
        return sum(1 for decision in self.decisions if decision.spread)

    @property
    def failed_count(self) -> int:
        """Return how many pages the model could not classify."""
        return sum(1 for decision in self.decisions if decision.error)


def detect_spread(
    page: Page,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    ns: str = "split",
    directory: str = "",
    base_width: int = 0,
) -> Spread:
    """Decide whether one page holds two pages side by side."""
    if not _is_candidate(page, base_width):
        return Spread()

    path = Path(directory) / page.filename
    prompt = split_prompt()

    if cache is None:
        return _ask_spread(client, prompt, path)

    key = fingerprint(
        file_fingerprint(path),
        prompt,
        *client.signature,
    )

    name = Path(page.filename).stem
    entry = cache.load_json(ns, name, key)
    if entry is not None:
        return Spread(
            spread=_as_bool(entry.get("spread")),
            reason=str(entry.get("reason") or ""),
        )

    result = _ask_spread(client, prompt, path)
    # Errors are never cached, so a failed page is retried next run.
    if not result.error:
        cache.save_json(ns, name, key, _spread_fields(result))
    return result


# Only a page about twice as wide as one page can hold two pages.
def _is_candidate(page: Page, base_width: int) -> bool:
    wide = base_width > 0 and page.width >= base_width * SPREAD_RATIO
    flat = page.height > 0 and page.width >= page.height * SPREAD_RATIO
    return wide or flat


# Ask the model with a downscaled copy of the page.
def _ask_spread(client: LLMClient, prompt: str, path: Path) -> Spread:
    try:
        with tempfile.TemporaryDirectory() as folder:
            thumb = _thumbnail(path, Path(folder))
            reply = client.chat(prompt, image_path=thumb)
        fields = extract_json(reply)
    except (LLMError, ValueError, OSError) as exc:
        return Spread(error=str(exc))

    return Spread(
        spread=_as_bool(fields.get("spread")),
        reason=str(fields.get("reason") or ""),
    )


# Shrink one page, keeping its shape so the gutter still shows.
def _thumbnail(path: Path, folder: Path) -> Path:
    target = folder / path.name
    with Image.open(path) as image:
        copy = image.convert("RGB")
        copy.thumbnail(THUMBNAIL_BOX, Image.LANCZOS)
        copy.save(target, "JPEG", quality=IMAGE_QUALITY)
    return target


# The model may answer with true, "true" or 1, so read all of them.
def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _spread_fields(spread: Spread) -> dict:
    return {"spread": spread.spread, "reason": spread.reason}


def split_book(
    book: Book,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    workers: int = 1,
    on_page: Callable[[Page, Spread, float], None] | None = None,
) -> Split:
    """Cut every two-page spread in half and renumber the pages."""
    assert workers >= 1

    ns = f"split/{book.id}"
    base = _base_width(book.pages)

    def run(page: Page) -> tuple[Page, Spread, float]:
        started = time.perf_counter()
        spread = detect_spread(
            page,
            client,
            cache=cache,
            ns=ns,
            directory=book.directory,
            base_width=base,
        )
        return page, spread, time.perf_counter() - started

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
            directory=book.directory,
            dpi=book.dpi,
            title=book.title,
        )
    )
    for page, spread, elapsed in results:
        split.decisions.append(spread)
        # One spread becomes two pages, so every index is set here.
        first = len(split.book.pages)
        split.book.pages.extend(_cut(page, spread, book.directory, first))
        if on_page is not None:
            on_page(page, spread, elapsed)
    return split


# The narrowest page is the one page of the book, so a spread is twice it.
def _base_width(pages: list[Page]) -> int:
    widths = [page.width for page in pages if page.width]
    return min(widths) if widths else 0


# Cut one page down the middle, or keep it whole when it holds one page.
def _cut(
    page: Page,
    spread: Spread,
    directory: str,
    start: int,
) -> list[Page]:
    if not spread.spread:
        return [
            Page(
                index=start,
                filename=page.filename,
                width=page.width,
                height=page.height,
                text=page.text,
            )
        ]

    source = Path(directory) / page.filename
    pages = []
    with Image.open(source) as image:
        width, height = image.size
        middle = width // 2
        boxes = ((0, 0, middle, height), (middle, 0, width, height))
        for offset, box in enumerate(boxes):
            target = source.with_name(f"{source.stem}{'ab'[offset]}.jpg")
            piece = image.convert("RGB").crop(box)
            piece.save(target, "JPEG", quality=IMAGE_QUALITY)
            # The text layer covers the whole spread, not one half of it.
            pages.append(
                Page(
                    index=start + offset,
                    filename=target.name,
                    width=piece.width,
                    height=piece.height,
                )
            )
    return pages


def save_split(
    split: Split,
    root: str | Path | None = None,
) -> Path:
    """Write the split book to <root>/<book_id>/split.json."""
    return write_json(split.book.id, "split", split.book.to_dict(), root)
