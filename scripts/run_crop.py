"""Run the crop stage from the command line.

Reads out/<book>/understand.json and cuts every panel box out of its page
image, so later stages crop nothing.

Usage:
    python scripts/run_crop.py C01
    python scripts/run_crop.py C01 --root /tmp/out
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.config import out_root
from aura_paper.stages.crop import crop

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the crop stage.")
    parser.add_argument("book", help="book id produced by run_understand.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser() if args.root else out_root()
    understand_path = root / args.book / "understand.json"
    if not understand_path.is_file():
        print(f"missing {understand_path}", file=sys.stderr)
        print("start with scripts/run_understand.py", file=sys.stderr)
        return 2

    print(f"book    {args.book}")
    print(f"root    {root}")
    print()

    started = time.perf_counter()
    result = crop(args.book, root=root)
    elapsed = time.perf_counter() - started

    print(f"panels  {len(result.panels)}")
    print(f"total   {elapsed:.1f}s")
    if result.error:
        print(f"error   {result.error}", file=sys.stderr)
        return 1

    print(f"output  {root / args.book / 'crop.json'}")
    print(f"folder  {root / args.book / 'panels'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
