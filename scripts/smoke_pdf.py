"""Manual smoke test for the PDF stage.

Renders a PDF into an image directory, reads whatever text layer it has,
and loads the result with Book so the handoff is visible.

Usage:
    python scripts/smoke_pdf.py <book.pdf>
    python scripts/smoke_pdf.py <book.pdf> --dpi 150 --quality 90
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.book import load_book
from aura_paper.config import load_env, out_root
from aura_paper.pdf import (
    DEFAULT_DPI,
    IMAGE_QUALITY,
    PdfPage,
    render_pdf,
    save_pages,
)

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PDF stage.")
    parser.add_argument("pdf", help="PDF file to render")
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"render resolution (default={DEFAULT_DPI})",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=IMAGE_QUALITY,
        help=f"jpeg quality (default={IMAGE_QUALITY})",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    source = Path(args.pdf).expanduser()
    if not source.is_file():
        print(f"not a PDF file: {source}", file=sys.stderr)
        return 2

    target = out_root() / source.stem / "pages"

    print(f"book    {source}")
    print(f"output  {target}")
    print(f"dpi     {args.dpi}  quality={args.quality}")
    print("rendering every page", flush=True)

    started = time.perf_counter()
    content = render_pdf(
        source,
        target,
        dpi=args.dpi,
        quality=args.quality,
        on_page=show,
    )
    elapsed = time.perf_counter() - started
    path = save_pages(content)

    book = load_book(content.directory, book_id=content.id)

    print()
    print(f"pages   {content.page_count}")
    print(f"text    {content.text_pages}")
    print(f"book    {book.page_count} pages loaded from the directory")
    print(f"total   {elapsed:.1f}s")
    print(f"file    {path}")
    return 0


# One line per page, so a long run still reads as a progress log.
def show(page: PdfPage, elapsed: float) -> None:
    size = f"{page.width}x{page.height}"
    head = f"{page.index + 1:02d}  {elapsed:5.1f}s  {size:<12}"
    print(f"{head} text={len(page.text)}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
