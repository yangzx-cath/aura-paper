"""Publish one book: copy the film, subtitles and facts into the library.

Reads out/<book>/compose.json and out/<book>/subtitles.vtt, then writes
data/books/<book>/pub/: film.mp4, subtitles.vtt, cover.jpg and
publish.json. The shelf shows the book 可观看 once publish.json is there.

Usage:
    python scripts/run_publish.py B005
    python scripts/run_publish.py B005 --library /tmp/library
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.config import books_dir, load_env, out_root
from aura_paper.stages.publish import publish

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy a finished book into the library."
    )
    parser.add_argument("book", help="book id produced by run_subtitles.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--library",
        default="",
        help="library root, default is data/books",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    library = Path(args.library).expanduser() if args.library else books_dir()
    compose_path = root / args.book / "compose.json"
    if not compose_path.is_file():
        print(f"missing {compose_path}", file=sys.stderr)
        print("run scripts/run_compose.py first", file=sys.stderr)
        return 2

    print(f"book     {args.book}")
    print(f"root     {root}")
    print(f"library  {library}")
    print()
    print("Packing the release", flush=True)

    started = time.perf_counter()
    result = publish(args.book, root=root, library=library)
    elapsed = time.perf_counter() - started

    print()
    if result.error:
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    print(f"title    {result.title or '（没有书名）'}")
    print(f"language {result.language or '（未判定）'}")
    print(f"seconds  {result.seconds:.2f}")
    print(f"cues     {result.cues}")
    print(f"film     {result.film}")
    print(f"vtt      {result.vtt}")
    print(f"cover    {result.cover or '（没有封面）'}")
    print(f"cast     {len(result.cast)}")
    print(f"total    {elapsed:.1f}s")
    print(f"output   {library / args.book / 'pub' / 'publish.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
