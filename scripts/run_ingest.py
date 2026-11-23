"""Run the ingest stage from the command line.

Renders a PDF into logical pages, asks the model where one image holds two
pages, and writes ingest.json for the next stage.

Usage:
    python scripts/run_ingest.py <book.pdf>
    python scripts/run_ingest.py <book.pdf> --pair-from 2
    python scripts/run_ingest.py <book.pdf> --dpi 200 --no-cache
    python scripts/run_ingest.py <book.pdf> --effort high
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.clients.llm import LLMClient
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.media.pdf import DEFAULT_DPI, DEFAULT_QUALITY, PdfError
from aura_paper.schema.book import Page
from aura_paper.stages.ingest import COVER_PAGES, ingest
from aura_paper.store.cache import Cache

ROOT = Path(__file__).resolve().parent.parent

# The layout question is simple, so the default does not burn reasoning.
DEFAULT_EFFORT = "low"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ingest stage.")
    parser.add_argument("pdf", help="PDF file to ingest")
    parser.add_argument(
        "--id",
        default="",
        help="book id, default is the PDF file name without suffix",
    )
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"render dpi (default={DEFAULT_DPI})",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_QUALITY,
        help=f"jpeg quality (default={DEFAULT_QUALITY})",
    )
    parser.add_argument(
        "--pair-from",
        type=int,
        default=COVER_PAGES,
        help=f"pages before this index never pair (default={COVER_PAGES})",
    )
    parser.add_argument(
        "--effort",
        default=DEFAULT_EFFORT,
        help=f"reasoning effort (default={DEFAULT_EFFORT})",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    source = Path(args.pdf).expanduser()
    if not source.is_file():
        print(f"not a PDF file: {source}", file=sys.stderr)
        return 2

    if args.dpi <= 0:
        print(f"dpi must be positive: {args.dpi}", file=sys.stderr)
        return 2
    if not 1 <= args.quality <= 100:
        print(f"quality must be 1-100: {args.quality}", file=sys.stderr)
        return 2
    if args.pair_from < 0:
        print(
            f"pair_from must be 0 or more: {args.pair_from}",
            file=sys.stderr,
        )
        return 2

    llm = LLMClient.from_env(args.effort)
    missing = llm.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)
    root = Path(args.root).expanduser() if args.root else out_root()
    book_id = args.id or source.stem

    print(f"pdf     {source}")
    print(f"book    {book_id}")
    print(f"model   {llm.model}  effort={llm.reasoning_effort or '-'}")
    print(f"root    {root}")
    print(f"dpi     {args.dpi}  pair_from={args.pair_from}")
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print()
    print("Rendering pages and checking every group", flush=True)

    started = time.perf_counter()
    try:
        book = ingest(
            source,
            book_id,
            llm=llm,
            root=root,
            dpi=args.dpi,
            quality=args.quality,
            pair_from=args.pair_from,
            cache=cache,
            on_page=_print_page,
        )
    except PdfError as exc:
        print(f"cannot read the pdf: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    failed = _failed_count(book.pages)
    print()
    print(f"source  {book.source_count} pages")
    print(f"logical {book.page_count} pages")
    print(f"origins {_origins_text(book.pages)}")
    print(f"failed  {failed}")
    print(f"total   {elapsed:.1f}s")
    print(f"stats   {cache.stats()}")
    if book.error:
        print(f"error   {book.error}", file=sys.stderr)
        return 1

    print(f"output  {root / book_id / 'ingest.json'}")
    return 0 if failed == 0 else 1


# Print one page as soon as it is written.
def _print_page(page: Page) -> None:
    status = page.error or page.origin
    print(f"{page.filename}  {page.width}x{page.height}  {status}", flush=True)


# Count the pages that carry an error.
def _failed_count(pages: list[Page]) -> int:
    return sum(1 for page in pages if page.error)


# Count the pages by how they were made.
def _origins_text(pages: list[Page]) -> str:
    counts = {"page": 0, "spread": 0, "half": 0}
    for page in pages:
        if page.origin in counts:
            counts[page.origin] += 1
    parts = []
    for name, count in counts.items():
        parts.append(f"{name}={count}")
    return "  ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
