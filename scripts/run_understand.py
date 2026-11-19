"""Run the understanding stage from the command line.

Reads out/<book>/book.json from the PDF stage, runs every page through the
vision model, and writes the result to content.json. A second run reuses
the cache and skips the model calls.

Usage:
    export LLM_API_KEY=sk-xxx
    python scripts/run_understand.py <book_id> [--no-cache] [--workers N]
"""

import argparse
import json
import sys
import time
from pathlib import Path
from threading import Lock

from aura_paper.book import Book, Page
from aura_paper.cache import Cache
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.llm import LLMClient
from aura_paper.understand import (
    PageContent,
    save_content,
    understand_book,
)

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the understanding stage."
    )
    parser.add_argument(
        "book",
        help="book id from run_pdf.py, the PDF name without suffix",
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

    book_path = out_root() / args.book / "book.json"
    if not book_path.is_file():
        print(f"missing {book_path}", file=sys.stderr)
        print("start with run_pdf.py", file=sys.stderr)
        return 2

    book = Book.from_dict(json.loads(book_path.read_text(encoding="utf-8")))

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
    print("Reading every page", flush=True)

    started = time.perf_counter()
    lock = Lock()

    def show(page: Page, result: PageContent, elapsed: float) -> None:
        with lock:
            print(_line(page, result, elapsed), flush=True)

    content = understand_book(
        book,
        client,
        cache=cache,
        workers=args.workers,
        on_page=show,
    )

    path = save_content(content)
    print()
    print(f"pages   {content.page_count}")
    print(f"failed  {content.failed_count}")
    print(f"title   {content.cover.title or '-'}")
    print(f"total   {time.perf_counter() - started:.1f}s")
    print(f"stats   {cache.stats()}")
    print(f"output  {path}")
    return 0 if content.failed_count == 0 else 1


# One line per page, so a long run still reads as a progress log.
def _line(page: Page, result: PageContent, elapsed: float) -> str:
    size = f"{page.width}x{page.height}"
    status = result.error or result.mood or "-"
    return f"{page.filename}  {size:<11} {elapsed:6.1f}s  {status}"


if __name__ == "__main__":
    raise SystemExit(main())
