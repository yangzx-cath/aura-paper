"""Lay every spoken line over the finished film as burnt-in subtitles.

Reads out/<book>/compose.json for where each take sits in the film and
out/<book>/jobs.json for the lines and their offsets, then writes
out/<book>/subtitles.ass and, by default, out/<book>/shots/film-subs.mp4.
The master film is left without words, so a second copy can be made any
time.

Usage:
    python scripts/run_subtitles.py C01
    python scripts/run_subtitles.py C01 --no-burn
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.config import load_env, out_root
from aura_paper.stages.subtitles import subtitles

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write the subtitle file and burn it into the film."
    )
    parser.add_argument("book", help="book id produced by run_compose.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--fonts",
        default="",
        help="font folder, default is data/fonts",
    )
    parser.add_argument(
        "--no-burn",
        action="store_true",
        help="write the subtitle file only",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    compose_path = root / args.book / "compose.json"
    if not compose_path.is_file():
        print(f"missing {compose_path}", file=sys.stderr)
        print("run scripts/run_compose.py first", file=sys.stderr)
        return 2

    burn = not args.no_burn
    print(f"book     {args.book}")
    print(f"root     {root}")
    print(f"burn     {burn}")
    print()
    print("Writing the subtitles", flush=True)

    started = time.perf_counter()
    result = subtitles(
        args.book,
        root=root,
        fonts=args.fonts or None,
        burn=burn,
    )
    elapsed = time.perf_counter() - started

    print()
    print(f"cues     {result.cues}")
    if result.file:
        print(f"file     {result.file}")
    if result.burned:
        print(f"burned   {result.burned}")
    print(f"total    {elapsed:.1f}s")
    if result.error:
        print()
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
