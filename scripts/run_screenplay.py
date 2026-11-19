"""Run the screenplay stage from the command line.

Reads out/<book>/content.json and story.json, writes the beat and lines of
every story page to screenplay.json.

Usage:
    export LLM_API_KEY=sk-xxx
    python scripts/run_screenplay.py <book_id>
    python scripts/run_screenplay.py <book_id> --workers 4
    python scripts/run_screenplay.py <book_id> --dump-prompt 12 > prompt.txt
"""

import argparse
import json
import sys
import time
from pathlib import Path
from threading import Lock

from aura_paper.cache import Cache
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.llm import LLMClient
from aura_paper.prompts import screenplay_prompt
from aura_paper.screenplay import PageScene, build_screenplay, save_screenplay
from aura_paper.story import Story
from aura_paper.understand import BookContent, PageContent

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the screenplay stage.")
    parser.add_argument("book", help="book id under the output directory")
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
        metavar="PAGE",
        help="print one page's prompt and exit without calling the model",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    folder = out_root() / args.book
    book_path = folder / "content.json"
    story_path = folder / "story.json"
    for path in (book_path, story_path):
        if not path.is_file():
            print(f"missing {path}", file=sys.stderr)
            print(
                "start with run_understand.py and run_story.py",
                file=sys.stderr,
            )
            return 2

    content = BookContent.from_dict(
        json.loads(book_path.read_text(encoding="utf-8"))
    )
    story = Story.from_dict(json.loads(story_path.read_text(encoding="utf-8")))

    if story.error:
        print(f"story error: {story.error}", file=sys.stderr)
        return 2

    if args.dump_prompt is not None:
        return _dump_prompt(content, story, args.dump_prompt)

    client = LLMClient.from_env()
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)
    print(f"book    {content.id}  story pages={len(content.story_pages)}")
    print(f"language {content.language}")
    print(f"model   {client.model}  timeout={client.timeout:.0f}s")
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print(f"workers {args.workers}")
    print()
    print("Writing the beat and lines of every page", flush=True)

    started = time.perf_counter()
    lock = Lock()

    def show(page: PageContent, scene: PageScene, elapsed: float) -> None:
        with lock:
            print(_line(page, scene, elapsed), flush=True)

    screenplay = build_screenplay(
        content,
        story,
        client,
        cache=cache,
        workers=args.workers,
        on_page=show,
    )
    elapsed = time.perf_counter() - started

    path = save_screenplay(screenplay)
    failed = [scene for scene in screenplay.pages if scene.error]

    print()
    print(f"pages   {screenplay.page_count}")
    print(f"failed  {len(failed)}")
    print(f"total   {elapsed:.1f}s")
    print(f"stats   {cache.stats()}")
    print(f"output  {path}")
    print()
    for scene in screenplay.pages:
        _show(scene)

    for scene in failed:
        page = scene.index + 1
        print(f"error   page {page}: {scene.error}", file=sys.stderr)
    return 0 if not failed else 1


# Print the prompt the model would receive, without spending a call.
def _dump_prompt(content: BookContent, story: Story, number: int) -> int:
    pages = content.story_pages
    if not 1 <= number <= content.page_count:
        print(f"page out of range: {number}", file=sys.stderr)
        return 2

    page = content.pages[number - 1]
    if page not in pages:
        print(f"page {number} is not a story page", file=sys.stderr)
        return 2

    previous = ""
    position = pages.index(page)
    if position > 0:
        before = pages[position - 1]
        previous = before.page_text or before.description

    prompt = screenplay_prompt(
        page, story, previous=previous, language=content.language
    )
    print(f"prompt length: {len(prompt)}", file=sys.stderr)
    print(prompt)
    return 0


# One line per page, so a long run still reads as a progress log.
def _line(page: PageContent, scene: PageScene, elapsed: float) -> str:
    status = scene.error or f"{scene.duration}s"
    return f"{page.index + 1:02d}  {elapsed:6.1f}s  {status}  {scene.beat}"


# Keep one scene to a few lines, so a long book still fits one screen.
def _show(scene: PageScene) -> None:
    status = f"{scene.duration}s" if not scene.error else scene.error
    print(f"{scene.index + 1:02d}  {status}")
    print(f"    beat  {scene.beat}")
    for line in scene.lines:
        who = line.speaker or "-"
        print(f"    {line.kind[:3]}   {who:10} {line.text}")


if __name__ == "__main__":
    raise SystemExit(main())
