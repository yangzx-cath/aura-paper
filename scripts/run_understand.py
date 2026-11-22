"""Run the understand stage from the command line.

Reads out/<book>/ingest.json, reads every page image, and writes
understand.json for the next stage.

Usage:
    python scripts/run_understand.py C01
    python scripts/run_understand.py C01 --workers 4
    python scripts/run_understand.py C01 --effort high
"""

import argparse
import sys
import time
from functools import partial
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.llm import LLMClient
from aura_paper.media.image import ink_coverage, load_image
from aura_paper.schema.content import PageContent
from aura_paper.stages.understand import understand

ROOT = Path(__file__).resolve().parent.parent

# An empty effort keeps LLM_REASONING_EFFORT from the environment.
DEFAULT_EFFORT = ""

# Pages below this share of ink inside the boxes are reported.
COVERAGE_LIMIT = 0.75


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the understand stage.")
    parser.add_argument("book", help="book id produced by run_ingest.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="pages to read at once (default=4)",
    )
    parser.add_argument(
        "--effort",
        default=DEFAULT_EFFORT,
        help="reasoning effort, empty keeps the env setting",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    if args.workers < 1:
        print(f"workers must be 1 or more: {args.workers}", file=sys.stderr)
        return 2

    root = Path(args.root).expanduser() if args.root else out_root()
    ingest_path = root / args.book / "ingest.json"
    if not ingest_path.is_file():
        print(f"missing {ingest_path}", file=sys.stderr)
        print("start with scripts/run_ingest.py", file=sys.stderr)
        return 2

    llm = LLMClient.from_env(args.effort)
    missing = llm.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)

    print(f"book    {args.book}")
    print(f"model   {llm.model}  effort={llm.reasoning_effort or '-'}")
    print(f"root    {root}")
    print(f"workers {args.workers}")
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print()
    print("Understanding every page", flush=True)

    started = time.perf_counter()
    content = understand(
        args.book,
        llm=llm,
        root=root,
        workers=args.workers,
        cache=cache,
        on_page=partial(
            _print_page,
            pages_dir=root / args.book / "pages",
        ),
    )
    elapsed = time.perf_counter() - started

    failed = _failed_count(content.pages)
    print()
    print(f"pages   {content.page_count}")
    print(f"failed  {failed}")
    print(f"total   {elapsed:.1f}s")
    print(f"stats   {cache.stats()}")
    if content.page_count == 0:
        print("error   ingest.json has no pages", file=sys.stderr)
        return 1

    print(f"output  {root / args.book / 'understand.json'}")
    print(f"panels  {root / args.book / 'panels'}")
    return 0 if failed == 0 else 1


# Print one page as soon as it is read.
def _print_page(
    page: PageContent,
    elapsed: float,
    *,
    pages_dir: Path,
) -> None:
    status = page.error or "ok"
    note = _coverage_note(page, pages_dir)
    text = f"{page.filename}  {elapsed:6.1f}s  {status}  {page.light}{note}"
    print(text, flush=True)


# Report how much of the page ink the panel boxes hold, when it is low.
def _coverage_note(page: PageContent, pages_dir: Path) -> str:
    boxes = []
    for panel in page.panels:
        box = panel.box
        if box is None:
            continue
        left, top, right, bottom = box
        boxes.append((left, top, right, bottom))
    if not boxes:
        return ""
    image = load_image(pages_dir / page.filename)
    share = ink_coverage(image, boxes)
    if share >= COVERAGE_LIMIT:
        return ""
    return f"  框覆盖 {share:.0%}"


# Count the pages that carry an error.
def _failed_count(pages: list[PageContent]) -> int:
    return sum(1 for page in pages if page.error)


if __name__ == "__main__":
    raise SystemExit(main())
