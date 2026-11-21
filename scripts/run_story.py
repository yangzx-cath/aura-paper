"""Run the story stage from the command line.

Reads out/<book>/content.json, derives the story context and writes
story.json next to it.

Usage:
    export LLM_API_KEY=sk-xxx
    python scripts/run_story.py <book_id>
    python scripts/run_story.py <book_id> --no-cache
    python scripts/run_story.py <book_id> --dump-prompt > prompt.txt
"""

import argparse
import json
import sys
import time
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.llm import LLMClient
from aura_paper.prompts import story_prompt
from aura_paper.story import build_story, save_story
from aura_paper.understand import BookContent

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the story stage.")
    parser.add_argument(
        "book",
        help="book id from run_pdf.py, the PDF name without suffix",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    parser.add_argument(
        "--dump-prompt",
        action="store_true",
        help="print the prompt and exit without calling the model",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    source = out_root() / args.book / "content.json"
    if not source.is_file():
        print(f"missing {source}", file=sys.stderr)
        print("start with run_understand.py", file=sys.stderr)
        return 2

    data = json.loads(source.read_text(encoding="utf-8"))
    content = BookContent.from_dict(data)

    if not content.story_pages:
        print("no story pages in content.json", file=sys.stderr)
        print("check the split and understand stages", file=sys.stderr)
        return 2

    if args.dump_prompt:
        prompt = story_prompt(content)
        print(f"prompt length: {len(prompt)}", file=sys.stderr)
        print(prompt)
        return 0

    client = LLMClient.from_env()
    missing = client.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)
    print(f"book    {content.id}  story pages={len(content.story_pages)}")
    print(f"title   {content.cover.title or '-'}")
    print(
        f"model   {client.model}  effort={client.reasoning_effort or '-'}"
        f"  timeout={client.timeout:.0f}s"
    )
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print()
    print("Asking the model for the story context", flush=True)

    started = time.perf_counter()
    story = build_story(content, client, cache=cache)
    elapsed = time.perf_counter() - started

    if story.error:
        print(f"failed  {story.error}", file=sys.stderr)
        return 1

    path = save_story(story)
    print(f"time    {elapsed:.1f}s")
    print(f"stats   {cache.stats()}")
    print(f"chars      {'、'.join(story.characters)}")
    print(f"found      {len(story.identified)}")
    print(f"refs       {len(story.references)}")
    print(f"setting    {story.setting}")
    print(f"style      {story.style}")
    print(f"resolved   {len(story.resolved)}")
    print(f"unresolved {len(story.unresolved)}")
    print()
    print("summary")
    print(story.summary)
    print()
    for item in story.identified:
        where = f"p{item.page:<3} #{item.figure}"
        print(f"who  {where} {item.name}  {item.evidence}")
    if story.identified:
        print()
    for item in story.references:
        print(f"ref  p{item.page:<3} #{item.figure} {item.name}  {item.why}")
    if story.references:
        print()
    print(f"output  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
