"""Manual smoke test for one page video.

Reads out/<book>/book.json and story.json, generates one page clip and
writes it to out/<book>/clips/page_01.mp4.

Usage:
    export MINIMAX_API_KEY=sk-xxx
    python scripts/smoke_video.py [book_id]
    python scripts/smoke_video.py [book_id] --page 2
    python scripts/smoke_video.py --dry-run
"""

import argparse
import json
import sys
import time
from pathlib import Path

from aura_paper.config import load_env, out_root
from aura_paper.minimax import MiniMaxClient
from aura_paper.prompts import shot_prompt
from aura_paper.story import Story
from aura_paper.understand import BookContent
from aura_paper.video import clip_path, generate_clip

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOOK = "chicken_and_sunflower"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one page video.")
    parser.add_argument("book", nargs="?", default=DEFAULT_BOOK)
    parser.add_argument(
        "--page",
        type=int,
        default=2,
        help="1-based page; default 2 skips the cover",
    )
    parser.add_argument("--duration", type=int, default=6)
    parser.add_argument("--resolution", default="768P")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the prompt and exit without calling the model",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    book_dir = out_root() / args.book
    book_path = book_dir / "book.json"
    story_path = book_dir / "story.json"
    for path in (book_path, story_path):
        if not path.is_file():
            print(f"missing {path}", file=sys.stderr)
            print(
                "run smoke_understand.py and smoke_story.py first",
                file=sys.stderr,
            )
            return 2

    content = BookContent.from_dict(
        json.loads(book_path.read_text(encoding="utf-8"))
    )
    story = Story.from_dict(json.loads(story_path.read_text(encoding="utf-8")))

    if not 1 <= args.page <= content.page_count:
        print(f"page out of range: {args.page}", file=sys.stderr)
        return 2
    page = content.pages[args.page - 1]

    if story.error:
        print(f"story error: {story.error}", file=sys.stderr)
        return 2
    if len(story.beats) != content.page_count:
        print("story beats do not match page count", file=sys.stderr)
        return 2

    previous = ""
    if page.index > 0:
        previous = story.beats[page.index - 1]
    prompt = shot_prompt(page, story, previous=previous)

    if args.dry_run:
        print(f"prompt length: {len(prompt)}", file=sys.stderr)
        print(prompt)
        return 0

    client = MiniMaxClient.from_env()
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    print(f"book    {content.id}  pages={content.page_count}")
    print(f"page    {args.page}  {page.filename}")
    print(f"model   {client.model}  timeout={client.timeout:.0f}s")
    print(f"video   {args.duration}s  {args.resolution}")
    print(
        f"wait    poll={client.poll_interval:.0f}s  "
        f"max={client.max_wait:.0f}s"
    )
    print("asking MiniMax for one clip", flush=True)

    started = time.perf_counter()
    clip = generate_clip(
        content,
        page,
        story,
        client,
        duration=args.duration,
        resolution=args.resolution,
    )
    elapsed = time.perf_counter() - started

    if clip.error:
        print(f"failed  {clip.error}", file=sys.stderr)
        return 1

    path = clip_path(content.id, page.index)
    size = path.stat().st_size if path.is_file() else 0
    print(f"time    {elapsed:.1f}s")
    print(f"task    {clip.task_id}")
    print(f"file    {path}  {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
