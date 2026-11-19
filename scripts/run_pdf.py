"""Run the PDF stage from the command line.

Renders a PDF into page images, reads whatever text layer it has, and
writes book.json for the next stage.

Usage:
    python scripts/run_pdf.py <book.pdf>
    python scripts/run_pdf.py <book.pdf> --dpi 150 --quality 90
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.book import Page, save_book
from aura_paper.config import load_env, out_root
from aura_paper.pdf import (
    DEFAULT_DPI,
    IMAGE_QUALITY,
    MAX_DPI,
    MAX_QUALITY,
    MIN_DPI,
    MIN_QUALITY,
    render_pdf,
)

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PDF stage.")
    parser.add_argument("pdf", help="PDF file to render")
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"render dpi, {MIN_DPI}-{MAX_DPI}, clamped to that range "
        f"(default={DEFAULT_DPI})",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=IMAGE_QUALITY,
        help=f"jpeg quality, {MIN_QUALITY}-{MAX_QUALITY} "
        f"(default={IMAGE_QUALITY})",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    source = Path(args.pdf).expanduser()
    if not source.is_file():
        print(f"not a PDF file: {source}", file=sys.stderr)
        return 2

    if not MIN_QUALITY <= args.quality <= MAX_QUALITY:
        print(
            f"quality must be {MIN_QUALITY}-{MAX_QUALITY}: {args.quality}",
            file=sys.stderr,
        )
        return 2

    target = out_root() / source.stem / "pages"

    print(f"book    {source}")
    print(f"output  {target}")
    print(f"dpi     {args.dpi}  quality={args.quality}")
    print()
    print("Rendering every page", flush=True)

    started = time.perf_counter()
    book = render_pdf(
        source,
        target,
        dpi=args.dpi,
        quality=args.quality,
        on_page=show,
    )
    elapsed = time.perf_counter() - started
    path = save_book(book)

    print()
    print(f"pages   {book.page_count}")
    print(f"text    {book.text_pages}")
    print(f"total   {elapsed:.1f}s")
    print(f"file    {path}")
    return 0


# One line per page, so a long run still reads as a progress log.
def show(page: Page, elapsed: float) -> None:
    size = f"{page.width}x{page.height}"
    head = f"{page.index:02d}  {elapsed:5.1f}s  {size:<12}"
    print(f"{head} text={len(page.text)}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
