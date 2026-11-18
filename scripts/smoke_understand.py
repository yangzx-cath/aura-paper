"""Manual smoke test for the whole understanding pipeline.

Reads a picture book directory, runs every page through the vision model,
and writes the result to the output directory. A second run reuses the
cache and skips the model calls.

Usage:
    export LLM_API_KEY=sk-xxx
    python scripts/smoke_understand.py <book_dir> [--book-id ID]
        [--no-cache] [--workers N]
"""

import argparse
import sys
import time
from pathlib import Path
from threading import Lock

from aura_paper.book import Book, PageImage, load_book
from aura_paper.cache import Cache
from aura_paper.config import cache_root, load_env
from aura_paper.llm import LLMClient
from aura_paper.understand import (
    PageContent,
    save_book,
    understand_book,
)

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the understanding pipeline."
    )
    parser.add_argument("book", help="directory holding the page images")
    parser.add_argument(
        "--book-id",
        default="",
        help="book id; defaults to the directory name",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="number of pages to run in parallel (default=1)",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    source = Path(args.book)
    if not source.is_dir():
        print(f"not a book directory: {source}", file=sys.stderr)
        return 2

    book = load_book(source, book_id=args.book_id)
    _mark_spreads(book)

    client = LLMClient.from_env()
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)
    print(f"book    {book.id}  pages={book.page_count}")
    print(f"model   {client.model}")
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print(f"workers {args.workers}")
    print()

    started = time.perf_counter()
    lock = Lock()

    def show(page: PageImage, result: PageContent, elapsed: float) -> None:
        with lock:
            print(_line(page, result, elapsed), flush=True)

    content = understand_book(
        book,
        client,
        cache=cache,
        workers=args.workers,
        on_page=show,
    )

    path = save_book(content)
    print()
    print(f"pages   {content.page_count}")
    print(f"failed  {content.failed_count}")
    print(f"total   {time.perf_counter() - started:.1f}s")
    print(f"stats   {cache.stats()}")
    print(f"output  {path}")
    return 0 if content.failed_count == 0 else 1


# A landscape scan holds two book pages, so treat it as a spread.
def _mark_spreads(book: Book) -> None:
    for page in book.pages:
        wide = bool(page.width and page.height and page.width > page.height)
        page.kind = "spread" if wide else "single"


# One line per page, so a long run still reads as a progress log.
def _line(page: PageImage, result: PageContent, elapsed: float) -> str:
    status = result.error or result.mood or "-"
    return f"{page.filename}  {page.kind:<6} {elapsed:6.1f}s  {status}"


if __name__ == "__main__":
    raise SystemExit(main())
