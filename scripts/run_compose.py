"""Mix one take per shot: the rendered clip with the spoken lines under it.

Reads out/<book>/jobs.json and render.json, builds the sound track of every
shot from the line files and the offsets jobs.json settled, and writes
out/<book>/shots/<shot>.mp4. Shots are not joined yet.

Usage:
    python scripts/run_compose.py C01
    python scripts/run_compose.py C01 --shot j7
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.config import load_env, out_root
from aura_paper.media import ffmpeg
from aura_paper.schema.compose import ComposedShot
from aura_paper.stages.compose import compose

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Mix one take per shot.")
    parser.add_argument("book", help="book id produced by run_render.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--shot",
        default="",
        metavar="镜号",
        help="mix one shot only",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    for name, stage in (("jobs", "jobs"), ("render", "render")):
        path = root / args.book / f"{name}.json"
        if not path.is_file():
            print(f"missing {path}", file=sys.stderr)
            print(f"run scripts/run_{stage}.py first", file=sys.stderr)
            return 2

    missing = ffmpeg.missing_tools()
    if missing:
        print("missing tools: " + ", ".join(missing), file=sys.stderr)
        return 2

    print(f"book     {args.book}")
    print(f"root     {root}")
    if args.shot:
        print(f"shot     {args.shot}")
    print()
    print("Mixing the takes", flush=True)

    started = time.perf_counter()
    result = compose(args.book, only=args.shot, root=root)
    elapsed = time.perf_counter() - started

    print()
    for shot in result.shots:
        print(_shot_line(shot))
    done = [shot for shot in result.shots if shot.file]
    print()
    print(f"takes    {len(done)}")
    print(f"seconds  {sum(shot.seconds for shot in done):.1f}")
    print(f"sound    {sum(1 for shot in done if shot.sound)} 镜带原声")
    print()
    print(f"total    {elapsed:.1f}s")
    print(f"output   {root / args.book / 'compose.json'}")
    if result.error:
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    return 0


# Print one take with its length and whether the clip brought sound.
def _shot_line(shot: ComposedShot) -> str:
    if shot.error:
        return f"{shot.shot:5} 跳过   {shot.error}"
    sound = "原声" if shot.sound else "静音"
    return f"{shot.shot:5} {shot.seconds:6.2f}s {sound}  {shot.file}"


if __name__ == "__main__":
    raise SystemExit(main())
