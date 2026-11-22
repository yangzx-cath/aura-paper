"""Build the reference images for one book's cast and places.

Reads out/<book>/understand.json, crops the figures that can stand alone,
asks the model which crops show the same character, then asks which panels
share a place. Writes cast.json and locations.json.

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
from aura_paper.schema.cast import Cast
from aura_paper.schema.location import Location
from aura_paper.stages.assets import assets

ROOT = Path(__file__).resolve().parent.parent

# Reading pages and grouping crops does not need deep thinking.
DEFAULT_EFFORT = "low"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the cast and place reference images."
    )
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
    print("Building the reference images", flush=True)

    started = time.perf_counter()

    cast_book, places = assets(args.book, llm=llm, root=root, cache=cache)
    elapsed = time.perf_counter() - started

    print()
    print(f"cast     {len(cast_book.cast)}")
    print(f"crops    {len(cast_book.figure_cast)}")
    print(f"resolved {len(cast_book.resolved)}  open {len(cast_book.open)}")
    for member in cast_book.cast:
        print(_cast_line(member))
    loose = sum(1 for item in places.panel_locations if not item.location)
    print()
    print(f"style    {places.style}")
    print(f"places   {len(places.locations)}  unplaced {loose}")
    for location in places.locations:
        print(_location_line(location))
    print()
    print(f"total    {elapsed:.1f}s")
    print(f"output   {root / args.book / 'cast.json'}")
    print(f"output   {root / args.book / 'locations.json'}")
    errors = [text for text in (cast_book.error, places.error) if text]
    for text in errors:
        print(f"error    {text}", file=sys.stderr)
    return 1 if errors else 0


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
