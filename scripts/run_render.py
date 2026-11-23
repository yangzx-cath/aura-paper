"""Generate one video clip per shot.

Reads out/<book>/jobs.json and calls the video model once per shot. The
clip is saved to out/<book>/clips/<shot>.mp4 and every task id, wall time
and error is written to render.json. A clip whose job did not change is
read from the cache instead of being generated again.

Usage:
    python scripts/run_render.py C01
    python scripts/run_render.py C01 --shot j1
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.clients.providers import make_video_client
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.schema.render import ShotRender
from aura_paper.stages.render import render

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate one video clip per shot."
    )
    parser.add_argument("book", help="book id produced by run_jobs.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--shot",
        default="",
        metavar="镜号",
        help="generate one shot only",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    jobs_path = root / args.book / "jobs.json"
    if not jobs_path.is_file():
        print(f"missing {jobs_path}", file=sys.stderr)
        print("run scripts/run_jobs.py first", file=sys.stderr)
        return 2

    client = make_video_client()
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)

    print(f"book     {args.book}")
    print(f"model    {client.model}")
    print(f"root     {root}")
    print(f"cache    {cache.root}  enabled={cache.enabled}")
    if args.shot:
        print(f"shot     {args.shot}")
    print()
    print("Generating the clips", flush=True)

    started = time.perf_counter()
    result = render(
        args.book,
        client=client,
        only=args.shot,
        root=root,
        cache=cache,
    )
    elapsed = time.perf_counter() - started

    print()
    for shot in result.shots:
        print(_shot_line(shot))
    generated = [shot for shot in result.shots if not shot.cached]
    failed = [shot for shot in result.shots if shot.error]
    print()
    print(f"clips    {len(result.shots)}")
    print(f"new      {len(generated) - len(failed)}")
    print(f"cached   {len(result.shots) - len(generated)}")
    print(f"failed   {len(failed)}")
    print(f"seconds  {sum(shot.duration for shot in result.shots)}")
    print()
    print(f"total    {elapsed:.1f}s")
    print(f"output   {root / args.book / 'render.json'}")
    if result.error:
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    return 0


# Print one clip with its task id and how long the call took.
def _shot_line(shot: ShotRender) -> str:
    if shot.error:
        return f"{shot.shot:5} 失败   {shot.error}"
    if shot.cached:
        return f"{shot.shot:5} 缓存   {shot.file}"
    return (
        f"{shot.shot:5} {shot.duration:2}s {shot.seconds:6.1f}s"
        f" {shot.task_id}  {shot.file}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
