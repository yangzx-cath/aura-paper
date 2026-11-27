"""Name the people in the panels that show a character only in part.

Only the pages where understand.json found a figure that is 半身, 部分遮挡 or
has no box are read again, this time with the character references at hand:
a page where everyone is shown whole needs no second look.

Writes out/<book>/identify.json, which the storyboard and jobs stages read
to know who is in which panel.

Usage:
    python scripts/run_identify.py C01
    python scripts/run_identify.py C01 --page p002
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.clients.llm import LLMClient
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.schema.content import PageContent
from aura_paper.schema.identify import PanelPeople
from aura_paper.stages.identify import identify
from aura_paper.store.cache import Cache

ROOT = Path(__file__).resolve().parent.parent

# Reading a panel and matching clothes needs no deep thinking.
DEFAULT_EFFORT = "low"

# Pages read at once: each page is a separate call with no shared state.
DEFAULT_WORKERS = 6


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Name the people in the partly shown panels."
    )
    parser.add_argument("book", help="book id produced by run_assets.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--page",
        default="",
        metavar="PAGE",
        help="read one page only, like p002",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"pages to read at once (default={DEFAULT_WORKERS})",
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

    root = Path(args.root).expanduser() if args.root else out_root()
    for name, stage in (("understand", "understand"), ("cast", "assets")):
        path = root / args.book / f"{name}.json"
        if not path.is_file():
            print(f"missing {path}", file=sys.stderr)
            print(f"run scripts/run_{stage}.py first", file=sys.stderr)
            return 2

    llm = LLMClient.from_env(args.effort)
    missing = llm.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)

    print(f"book     {args.book}")
    print(f"model    {llm.model}  effort={llm.reasoning_effort or '-'}")
    print(f"root     {root}")
    print(f"cache    {cache.root}  enabled={cache.enabled}")
    print(f"workers  {args.workers}")
    if args.page:
        print(f"page     {args.page}")
    print()
    print("Naming the people", flush=True)

    started = time.perf_counter()
    result = identify(
        args.book,
        llm=llm,
        only=args.page,
        workers=args.workers,
        root=root,
        cache=cache,
        on_page=_print_page,
    )
    elapsed = time.perf_counter() - started

    print()
    for panel in result.panels:
        print(_panel_line(panel))
    print()
    print(f"panels   {len(result.panels)}")
    print(f"named    {sum(len(panel.people) for panel in result.panels)}")
    print()
    print(f"total    {elapsed:.1f}s")
    print(f"output   {root / args.book / 'identify.json'}")
    if result.error:
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    return 0


# Print one page as soon as it is read.
def _print_page(page: PageContent, named: int, elapsed: float) -> None:
    print(
        f"{page.filename}  {elapsed:6.1f}s  {named} 人",
        flush=True,
    )


# Print one panel with everyone named in it.
def _panel_line(panel: PanelPeople) -> str:
    people = "；".join(
        f"{person.cast} {person.parts}" for person in panel.people
    )
    return f"{panel.page} #{panel.panel} {people or '（没人）'}"


if __name__ == "__main__":
    raise SystemExit(main())
