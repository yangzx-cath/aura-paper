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

from aura_paper.clients.tts import TTSClient
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.media import ffmpeg
from aura_paper.schema.compose import ComposedShot
from aura_paper.stages.compose import compose
from aura_paper.store.cache import Cache

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
        metavar="SHOT",
        help="mix one shot only",
    )
    parser.add_argument(
        "--no-title-card",
        action="store_true",
        help="leave the title card off the film",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
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

    cache = Cache(cache_root(), enabled=not args.no_cache)
    tts = None if args.no_title_card else TTSClient.from_env()
    if tts is not None and tts.missing_settings():
        print(
            "missing config for the title card: "
            + ", ".join(tts.missing_settings()),
            file=sys.stderr,
        )
        tts = None

    print(f"book     {args.book}")
    print(f"root     {root}")
    if args.shot:
        print(f"shot     {args.shot}")
    print()
    print("Mixing the takes", flush=True)

    started = time.perf_counter()
    result = compose(
        args.book,
        only=args.shot,
        tts=tts,
        root=root,
        cache=cache,
    )
    elapsed = time.perf_counter() - started

    print()
    for shot in result.shots:
        print(_shot_line(shot))
    done = [shot for shot in result.shots if shot.file]
    print()
    if result.joins:
        print("joins")
        for join in result.joins:
            print(
                f"  {join.before}→{join.after}"
                f"  {join.kind}  帧差 {join.jump:5.1f}"
            )
        print()
    print(f"takes    {len(done)}")
    print(f"seconds  {sum(shot.seconds for shot in done):.1f}")
    print(f"sound    {sum(1 for shot in done if shot.sound)} 镜带原声")
    if result.title_card:
        print(f"title    {result.title_card}")
    if result.film:
        print(f"film     {result.film}  {result.seconds:.1f}s")
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
