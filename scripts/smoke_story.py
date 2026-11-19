"""Manual smoke test for the story stage.

Reads out/<book>/content.json, derives the story context and writes
story.json next to it.

Usage:
    export LLM_API_KEY=sk-xxx
    python scripts/smoke_story.py <book_id>
    python scripts/smoke_story.py <book_id> --dump-prompt > prompt.txt
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
    parser.add_argument("book", help="book id under the output directory")
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
        print("run smoke_understand.py first", file=sys.stderr)
        return 2

    data = json.loads(source.read_text(encoding="utf-8"))
    content = BookContent.from_dict(data)

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

    cache = Cache(cache_root())
    print(f"book    {content.id}  pages={content.page_count}")
    print(f"model   {client.model}  timeout={client.timeout:.0f}s")
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print("asking the model for the story context", flush=True)

    started = time.perf_counter()
    story = build_story(content, client, cache=cache)
    elapsed = time.perf_counter() - started

    if story.error:
        print(f"failed  {story.error}", file=sys.stderr)
        return 1

    path = save_story(story)
    print(f"time    {elapsed:.1f}s")
    print(f"stats   {cache.stats()}")
    print(f"chars   {'、'.join(story.characters)}")
    print(f"setting {story.setting}")
    print(f"style   {story.style}")
    print()
    print("summary")
    print(story.summary)
    print()
    print(f"output  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
