"""Build one video generation job per shot.

Reads out/<book>/shots.json, voice.json, cast.json and locations.json, then
writes jobs.json: for every shot the prompt, the reference images, the
length, the aspect and the sound placed on its timeline. Nothing is paid
here, so the jobs can be read and edited before any video is generated.

Usage:
    python scripts/run_jobs.py C01
    python scripts/run_jobs.py C01 --shot j7
"""

import argparse
import sys
from pathlib import Path

from aura_paper.config import load_env, out_root
from aura_paper.schema.job import BookJobs, Job
from aura_paper.stages.jobs import jobs

ROOT = Path(__file__).resolve().parent.parent

# Debug size: small and cheap to generate.
DEFAULT_RESOLUTION = "480p"

# A square book fits a 4:3 frame better than a wide one.
DEFAULT_RATIO = "4:3"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build one video generation job per shot."
    )
    parser.add_argument("book", help="book id produced by run_voice.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--ratio",
        default=DEFAULT_RATIO,
        help=f"frame ratio of the video (default={DEFAULT_RATIO})",
    )
    parser.add_argument(
        "--resolution",
        default=DEFAULT_RESOLUTION,
        help=f"video size (default={DEFAULT_RESOLUTION})",
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        help="let the model add its own sound, off by default",
    )
    parser.add_argument(
        "--shot",
        default="",
        metavar="SHOT",
        help="print one job in full",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    for name, stage in (
        ("cast", "assets"),
        ("locations", "assets"),
        ("shots", "storyboard"),
        ("voice", "voice"),
    ):
        path = root / args.book / f"{name}.json"
        if not path.is_file():
            print(f"missing {path}", file=sys.stderr)
            print(f"run scripts/run_{stage}.py first", file=sys.stderr)
            return 2

    print(f"book     {args.book}")
    print(f"root     {root}")
    print(f"ratio    {args.ratio}")
    print(f"size     {args.resolution}")
    print(f"sound    {'model' if args.audio else 'off'}")
    print()
    print("Building the jobs", flush=True)

    result = jobs(
        args.book,
        ratio=args.ratio,
        resolution=args.resolution,
        audio=args.audio,
        root=root,
    )

    print()
    for job in result.shots:
        print(_job_line(job))
    print()
    print(f"jobs     {len(result.shots)}")
    print(f"seconds  {sum(job.duration for job in result.shots)}")
    print(f"images   {sum(len(job.images) for job in result.shots)}")
    print(f"lines    {sum(len(job.lines) for job in result.shots)}")
    print(f"output   {root / args.book / 'jobs.json'}")

    if args.shot:
        print()
        print(_detail(result, args.shot))
    if result.error:
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    return 0


# Print one job as a single line.
def _job_line(job: Job) -> str:
    sound = f"{job.audio_ms / 1000:5.1f}s"
    return (
        f"{job.shot:5} {job.duration:2}s {sound}"
        f" {len(job.images):2} 图 {len(job.lines):2} 句"
        f" {job.location or '（无场地）'}"
    )


# Print the whole job of one shot, so it can be read before spending.
def _detail(result: BookJobs, name: str) -> str:
    for job in result.shots:
        if job.shot != name:
            continue
        lines = [
            f"prompt：\n{job.prompt}",
            "",
            "images：",
        ]
        lines += [f"  {image.file}  {image.note}" for image in job.images]
        lines.append("")
        lines.append("lines：")
        lines += [
            f"  {line.start_ms / 1000:5.1f}s +{line.duration_ms / 1000:4.1f}s"
            f" {line.kind} {line.file or '（不配音）'} {line.text}"
            for line in job.lines
        ]
        return "\n".join(lines)
    return f"（没有 {name} 这一镜）"


if __name__ == "__main__":
    raise SystemExit(main())
