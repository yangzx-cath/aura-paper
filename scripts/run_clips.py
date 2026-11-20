"""Run the clips stage from the command line.

Reads out/<book>/content.json, story.json and screenplay.json, generates one
page clip and writes it to out/<book>/clips/page_XX.mp4.

Usage:
    export MINIMAX_API_KEY=sk-xxx
    python scripts/run_clips.py <book_id> --all
    python scripts/run_clips.py <book_id> --page 1
    python scripts/run_clips.py <book_id> --duration 8
    python scripts/run_clips.py <book_id> --dump-prompt
"""

import argparse
import json
import sys
import time
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.clips import build_clips, clip_path, generate_clip, save_clips
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.minimax import MiniMaxClient
from aura_paper.prompts import clip_prompt
from aura_paper.screenplay import Screenplay
from aura_paper.story import Story
from aura_paper.understand import BookContent

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the clips stage.")
    parser.add_argument(
        "book",
        help="book id from run_pdf.py, the PDF name without suffix",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="0-based page index; 0 is the cover, default 1 skips it",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="override the screenplay scene duration",
    )
    parser.add_argument("--resolution", default="768P")
    parser.add_argument(
        "--all",
        action="store_true",
        help="generate every planned page and write clips.json",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="clips to generate at once",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ask the API even when a clip is already on disk",
    )
    parser.add_argument(
        "--dump-prompt",
        action="store_true",
        help="print the prompt and exit without calling the model",
    )
    args = parser.parse_args()

    if args.all and args.dump_prompt:
        print("--dump-prompt prints one page; drop --all", file=sys.stderr)
        return 2

    load_env(ROOT / ".env")

    book_dir = out_root() / args.book
    book_path = book_dir / "content.json"
    story_path = book_dir / "story.json"
    screenplay_path = book_dir / "screenplay.json"
    for path in (book_path, story_path, screenplay_path):
        if not path.is_file():
            print(f"missing {path}", file=sys.stderr)
            print(
                "start with run_understand.py, run_story.py and "
                "run_screenplay.py",
                file=sys.stderr,
            )
            return 2

    content = BookContent.from_dict(
        json.loads(book_path.read_text(encoding="utf-8"))
    )
    story = Story.from_dict(json.loads(story_path.read_text(encoding="utf-8")))
    screenplay = Screenplay.from_dict(
        json.loads(screenplay_path.read_text(encoding="utf-8"))
    )

    if not 0 <= args.page < content.page_count:
        print(f"page index out of range: {args.page}", file=sys.stderr)
        return 2
    page = content.pages[args.page]

    if story.error:
        print(f"story error: {story.error}", file=sys.stderr)
        return 2
    if screenplay.error:
        print(f"screenplay error: {screenplay.error}", file=sys.stderr)
        return 2

    if args.all:
        return run_book(args, content, story, screenplay)

    scenes = {scene.index: scene for scene in screenplay.pages}
    scene = scenes.get(page.index)
    if scene is None:
        print(
            f"page index {args.page} has no screenplay scene; "
            "cover and back pages cannot be generated",
            file=sys.stderr,
        )
        return 2
    if scene.error:
        print(f"screenplay error: {scene.error}", file=sys.stderr)
        return 2

    seconds = args.duration
    if seconds is None:
        seconds = scene.duration

    prompt = clip_prompt(page, story, beat=scene.beat)

    if args.dump_prompt:
        print(f"scene   {seconds}s  {len(scene.lines)} lines", file=sys.stderr)
        print(f"beat    {scene.beat}", file=sys.stderr)
        print(f"prompt length: {len(prompt)}", file=sys.stderr)
        print(prompt)
        return 0

    client = MiniMaxClient.from_env()
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    print(f"book    {content.id}  pages={content.page_count}")
    print(f"index   {args.page}  {page.filename}")
    print(f"scene   {seconds}s  {len(scene.lines)} lines  {scene.beat}")
    print(f"model   {client.model}  timeout={client.timeout:.0f}s")
    print(f"clip    {seconds}s  {args.resolution}")
    print(
        f"wait    poll={client.poll_interval:.0f}s  "
        f"max={client.max_wait:.0f}s"
    )
    print()
    print("Asking MiniMax for one clip", flush=True)

    started = time.perf_counter()
    clip = generate_clip(
        content,
        page,
        story,
        scene,
        client,
        duration=args.duration,
        resolution=args.resolution,
    )
    elapsed = time.perf_counter() - started

    if clip.error:
        print(f"failed  {clip.error}", file=sys.stderr)
        return 1

    path = clip_path(content.id, page.filename)
    size = path.stat().st_size if path.is_file() else 0
    print(f"time    {elapsed:.1f}s")
    print(f"task    {clip.task_id}")
    print(f"file    {path}  {size:,} bytes")
    return 0


# Generate every planned page and write clips.json.
def run_book(
    args: argparse.Namespace,
    content: BookContent,
    story: Story,
    screenplay: Screenplay,
) -> int:
    client = MiniMaxClient.from_env()
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = None if args.no_cache else Cache(cache_root())

    print(f"book    {content.id}  pages={content.page_count}")
    print(f"scenes  {len(screenplay.pages)}")
    print(f"model   {client.model}  timeout={client.timeout:.0f}s")
    print(f"clips   {args.resolution}  workers={args.workers}")
    print(f"cache   {'off' if cache is None else cache.root}")
    print()
    print("Generating one clip per page", flush=True)

    def show(page, clip, elapsed):
        status = clip.error or f"{clip.duration}s"
        print(f"{page.index:02d}  {elapsed:6.1f}s  {status}", flush=True)

    clip_set = build_clips(
        content,
        story,
        screenplay,
        client,
        cache=cache,
        resolution=args.resolution,
        workers=args.workers,
        on_page=show,
    )
    path = save_clips(clip_set)

    print()
    print(f"clips   {clip_set.clip_count}  failed={clip_set.failed_count}")
    print(f"file    {path}")
    return 1 if clip_set.failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
