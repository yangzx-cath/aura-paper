"""Run the clips stage from the command line.

Reads out/<book>/content.json, story.json and screenplay.json, generates one
clip per page into out/<book>/clips/, and records the set in clips.json.

Usage:
    export AURA_VIDEO_PROVIDER=seedance
    export ARK_API_KEY=...
    python scripts/run_clips.py <book_id>
    python scripts/run_clips.py <book_id> --page 1
    python scripts/run_clips.py <book_id> --duration 8
    python scripts/run_clips.py <book_id> --dump-prompt 1
"""

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from threading import Lock

from aura_paper.cache import Cache
from aura_paper.clips import VideoClip, build_clips, save_clips
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.prompts1 import clip_prompt
from aura_paper.providers import make_video_client
from aura_paper.references import reference_path
from aura_paper.screenplay import Screenplay
from aura_paper.story import Story
from aura_paper.understand import BookContent, PageContent

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
        default=None,
        help="generate one page by 0-based index; default is every page",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="override the screenplay scene duration",
    )
    parser.add_argument(
        "--resolution",
        default=None,
        help="provider resolution preset; default is the provider's own",
    )
    parser.add_argument(
        "--provider",
        choices=("seedance", "minimax"),
        default=None,
        help="video provider; overrides AURA_VIDEO_PROVIDER",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="number of pages to run in parallel (default=1)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    parser.add_argument(
        "--dump-prompt",
        type=int,
        metavar="INDEX",
        help="print one page's prompt by 0-based index; 0 is the cover",
    )
    args = parser.parse_args()

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

    if story.error:
        print(f"story error: {story.error}", file=sys.stderr)
        return 2
    if screenplay.error:
        print(f"screenplay error: {screenplay.error}", file=sys.stderr)
        return 2

    if args.dump_prompt is not None:
        return _dump_prompt(content, story, screenplay, args.dump_prompt)

    if args.page is not None and not 0 <= args.page < content.page_count:
        print(f"page index out of range: {args.page}", file=sys.stderr)
        return 2

    plan = _plan(content, screenplay, args.page, args.duration)
    if plan is None:
        return 2

    client = make_video_client(args.provider)
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)
    print(f"book    {content.id}  pages={content.page_count}")
    print(f"client  {type(client).__name__}  model={client.model}")
    print(f"size    {args.resolution or 'provider default'}")
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print(f"workers {args.workers}")
    print()
    print("Generating one clip per page", flush=True)

    started = time.perf_counter()
    lock = Lock()
    beats = {scene.index: scene.beat for scene in plan.pages}

    def show(page: PageContent, clip: VideoClip, elapsed: float) -> None:
        with lock:
            print(_line(page, clip, beats[page.index], elapsed), flush=True)

    clip_set = build_clips(
        content,
        story,
        plan,
        client,
        cache=cache,
        resolution=args.resolution,
        workers=args.workers,
        on_page=show,
    )
    elapsed = time.perf_counter() - started

    path = save_clips(clip_set)
    print()
    print(f"clips   {clip_set.clip_count}")
    print(f"failed  {clip_set.failed_count}")
    print(f"total   {elapsed:.1f}s")
    print(f"stats   {cache.stats()}")
    print(f"output  {path}")
    return 0 if clip_set.failed_count == 0 else 1


# Select the scenes to run, applying the page and length overrides.
def _plan(
    content: BookContent,
    screenplay: Screenplay,
    page_index: int | None,
    duration: int | None,
) -> Screenplay | None:
    scenes = screenplay.pages
    if not scenes:
        print("no scene in screenplay.json", file=sys.stderr)
        print("check the screenplay stage", file=sys.stderr)
        return None

    if page_index is not None:
        index = content.pages[page_index].index
        scenes = [scene for scene in scenes if scene.index == index]
        if not scenes:
            print(
                f"page index {page_index} has no screenplay scene; "
                "the cover has none",
                file=sys.stderr,
            )
            return None

    if duration is not None:
        # The length goes into the cache key, so it belongs in the scene.
        scenes = [replace(scene, duration=duration) for scene in scenes]

    return Screenplay(
        id=screenplay.id,
        model=screenplay.model,
        pages=scenes,
    )


# Print one page's prompt without calling the model.
def _dump_prompt(
    content: BookContent,
    story: Story,
    screenplay: Screenplay,
    index: int,
) -> int:
    if not 0 <= index < content.page_count:
        print(f"page index out of range: {index}", file=sys.stderr)
        return 2

    page = content.pages[index]
    scenes = {scene.index: scene for scene in screenplay.pages}
    scene = scenes.get(page.index)
    if scene is None:
        print(
            f"page index {index} has no screenplay scene; "
            "the cover has none",
            file=sys.stderr,
        )
        return 2

    refs = [
        name
        for name in scene.characters
        if reference_path(content.id, name).is_file()
    ]
    prompt = clip_prompt(page, story, beat=scene.beat, characters=refs)
    head = f"scene   {scene.duration}s  {len(scene.lines)} lines"
    print(f"index   {index}  {page.filename}", file=sys.stderr)
    print(head, file=sys.stderr)
    print(f"beat    {scene.beat}", file=sys.stderr)
    print(f"images  1 page + {len(refs)} refs", file=sys.stderr)
    print(f"prompt length: {len(prompt)}", file=sys.stderr)
    print(prompt)
    return 0


# One line per page, so a long run still reads as a progress log.
def _line(
    page: PageContent,
    clip: VideoClip,
    beat: str,
    elapsed: float,
) -> str:
    status = clip.error or f"{clip.duration}s"
    return f"{page.filename}  {elapsed:6.1f}s  {status}  {beat}"


if __name__ == "__main__":
    raise SystemExit(main())
