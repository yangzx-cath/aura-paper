"""Group the figure crops into characters for one book.

Reads out/<book>/understand.json, keeps the figures that can stand alone
as a reference image, crops them, and asks the model which crops show the
same character.

Usage:
    python scripts/run_assets.py C01
    python scripts/run_assets.py C01 --effort low
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.clients.llm import LLMClient
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.schema.assets import Cast, Location
from aura_paper.stages.assets import assets

ROOT = Path(__file__).resolve().parent.parent

# Reading pages and grouping crops does not need deep thinking.
DEFAULT_EFFORT = "low"


def main() -> int:
    parser = argparse.ArgumentParser(description="Group figure crops.")
    parser.add_argument("book", help="book id produced by run_understand.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
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
    understand_path = root / args.book / "understand.json"
    if not understand_path.is_file():
        print(f"missing {understand_path}", file=sys.stderr)
        print("start with scripts/run_understand.py", file=sys.stderr)
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
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print()
    print("Grouping the figure crops", flush=True)

    started = time.perf_counter()

    result = assets(args.book, llm=llm, root=root, cache=cache)
    elapsed = time.perf_counter() - started

    print()
    print(f"cast     {len(result.cast)}")
    print(f"crops    {len(result.figure_cast)}")
    print(f"resolved {len(result.resolved)}  open {len(result.open)}")
    for member in result.cast:
        print(_cast_line(member))
    loose = sum(1 for item in result.panel_locations if not item.location)
    print()
    print(f"style    {result.style}")
    print(f"places   {len(result.locations)}  unplaced {loose}")
    for location in result.locations:
        print(_location_line(location))
    print()
    print(f"total    {elapsed:.1f}s")
    print(f"output   {root / args.book / 'assets.json'}")
    if result.error:
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    return 0


# Print one character with the crops chosen for it.
def _cast_line(member: Cast) -> str:
    name = member.name or "（无名）"
    pictures = "、".join(member.pictures) or "（无可用图）"
    return f"{member.id} {name}｜{member.look}｜{pictures}"


# Print one place with the crop that backs it.
def _location_line(location: Location) -> str:
    name = location.name or "（无名）"
    master = location.master or "（无母图）"
    return f"{location.id} {name}｜{location.light}｜{master}"


if __name__ == "__main__":
    raise SystemExit(main())
