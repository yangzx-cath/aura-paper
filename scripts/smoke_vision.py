"""Manual smoke test for the whole understanding pipeline.

Reads a picture book directory, runs every page through the vision model,
and writes the result to the output directory. A second run reuses the
cache and skips the model calls.

Usage:
    export VISION_API_KEY=sk-xxx
    python scripts/smoke_vision.py [book_dir] [--no-cache]
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.book import Book, PageImage
from aura_paper.cache import Cache
from aura_paper.config import cache_root, load_env
from aura_paper.understand import (
    BookContent,
    PageContent,
    save_book,
    understand_page,
)
from aura_paper.vision import VisionClient

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOOK = ROOT / "data" / "chicken_and_sunflower"


# A landscape scan holds two book pages, so treat it as a spread.
def _mark_spreads(book: Book) -> None:
    for page in book.pages:
        wide = bool(page.width and page.height and page.width > page.height)
        page.kind = "spread" if wide else "single"


# Format one progress line for a page that just finished.
def _line(page: PageImage, result: PageContent, elapsed: float) -> str:
    status = result.error or result.mood or "-"
    return f"{page.filename}  {page.kind:<6} {elapsed:6.1f}s  {status}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the understanding pipeline."
    )
    parser.add_argument("book", nargs="?", default=str(DEFAULT_BOOK))
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    source = Path(args.book)
    if not source.is_dir():
        print(f"not a book directory: {source}", file=sys.stderr)
        return 2

    book = Book(source.name)
    book.load(source)
    _mark_spreads(book)

    client = VisionClient.from_env()
    missing = [
        name
        for name, value in (
            ("VISION_BASE_URL", client.base_url),
            ("VISION_API_KEY", client.api_key),
            ("VISION_MODEL", client.model),
        )
        if not value
    ]
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)
    print(f"book   {book.id}  pages={book.page_count}")
    print(f"model  {client.model}")
    print(f"cache  {cache.root}  enabled={cache.enabled}")
    print()

    content = BookContent(id=book.id, title=book.title, source=book.source)
    ns = f"understand/{book.id}"
    started = time.perf_counter()

    for page in book.pages:
        page_started = time.perf_counter()
        result = understand_page(page, client, cache=cache, ns=ns)
        content.pages.append(result)
        print(_line(page, result, time.perf_counter() - page_started))

    path = save_book(content)
    print()
    print(f"total   {time.perf_counter() - started:.1f}s")
    print(f"failed  {content.failed_count}")
    print(f"stats   {cache.stats()}")
    print(f"output  {path}")
    return 0 if content.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
