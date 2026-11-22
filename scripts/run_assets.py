"""Pick the character reference crops for one book.

Reads out/<book>/understand.json, keeps the figures that can stand alone
as a reference image, and crops them to out/<book>/figures.

Usage:
    python scripts/run_assets.py C01
"""

import argparse
import sys
from pathlib import Path

from aura_paper.config import out_root
from aura_paper.stages.assets import FigurePick, pick_figures

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Pick reference crops.")
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
    print("Keeping the figures that can stand alone", flush=True)

    picks = pick_figures(args.book, root=root)

    print()
    print(f"kept    {len(picks)}")
    print(f"output  {root / args.book / 'figures'}")
    for pick in picks:
        print(_pick_line(pick))
    return 0 if picks else 1


# Print one pick with the fields that decide its place in the ranking.
def _pick_line(pick: FigurePick) -> str:
    return (
        f"{pick.file:16} {pick.facing}  面积 {pick.area:.2f}"
        f"  来自 {pick.page} fig{pick.figure}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
