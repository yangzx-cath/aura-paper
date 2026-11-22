"""Plan the scenes and shots of one book.

Reads out/<book>/understand.json, cast.json and locations.json, shrinks the
panel crops and the character reference images, and asks the model for the
scene and shot plan. Writes storyboard.json.

Usage:
    python scripts/run_storyboard.py C01
    python scripts/run_storyboard.py C01 --effort low
"""

import argparse
import json
import sys
import time
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.clients.llm import LLMClient
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.schema.scene import Scene
from aura_paper.schema.shot import BookShots, Shot
from aura_paper.stages.storyboard import storyboard

ROOT = Path(__file__).resolve().parent.parent

# Planning the whole book needs more than reading one page.
DEFAULT_EFFORT = "low"


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan the scenes and shots.")
    parser.add_argument("book", help="book id produced by run_understand.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--effort",
        default=DEFAULT_EFFORT,
        help=f"reasoning effort (default={DEFAULT_EFFORT})",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    for name in ("understand", "cast", "locations"):
        path = root / args.book / f"{name}.json"
        if not path.is_file():
            print(f"missing {path}", file=sys.stderr)
            print(
                "run scripts/run_understand.py and run_assets.py first",
                file=sys.stderr,
            )
            return 2

    llm = LLMClient.from_env(args.effort)
    missing = llm.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)

    print(f"book    {args.book}")
    print(f"model   {llm.model}  effort={llm.reasoning_effort or '-'}")
    print(f"root    {root}")
    print(f"cache   {cache.root}  enabled={cache.enabled}")
    print()
    print("Planning the scenes and shots", flush=True)

    started = time.perf_counter()

    scene_book, shot_book = storyboard(
        args.book,
        llm=llm,
        root=root,
        cache=cache,
    )
    elapsed = time.perf_counter() - started

    print()
    print(f"scenes   {len(scene_book.scenes)}")
    print(f"shots    {len(shot_book.shots)}")
    for scene in scene_book.scenes:
        print(_scene_line(scene, shot_book.shots))
    print()
    print(f"audio    {_kind_line(shot_book.shots)}")
    print(f"join     {_join_line(shot_book.shots)}")
    print(f"unused   {_unused_line(args.book, root, shot_book)}")
    print()
    print(f"total    {elapsed:.1f}s")
    print(f"output   {root / args.book / 'scenes.json'}")
    print(f"output   {root / args.book / 'shots.json'}")
    errors = [text for text in (scene_book.error, shot_book.error) if text]
    for text in errors:
        print(f"error    {text}", file=sys.stderr)
    return 1 if errors else 0


# Print one scene with the shots that belong to it.
def _scene_line(scene: Scene, shots: list[Shot]) -> str:
    own = [shot.id for shot in shots if shot.scene == scene.id]
    span = f"{own[0]}–{own[-1]}" if own else "（无镜头）"
    name = scene.name or "（无名）"
    place = scene.location or "（无场地）"
    return f"{scene.id} {name}｜{place}｜{span} 共 {len(own)} 镜"


# Count the sounds per kind.
def _kind_line(shots: list[Shot]) -> str:
    counts = {"旁白": 0, "对白": 0, "音效": 0}
    for shot in shots:
        for line in shot.audio:
            counts[line.kind] = counts.get(line.kind, 0) + 1
    return "  ".join(f"{kind} {count}" for kind, count in counts.items())


# Count the shots per join.
def _join_line(shots: list[Shot]) -> str:
    cut = sum(1 for shot in shots if shot.join == "硬切")
    fade = sum(1 for shot in shots if shot.join == "叠化")
    return f"硬切 {cut}  叠化 {fade}"


# Count the panels no shot uses.
def _unused_line(book_id: str, root: Path, shot_book: BookShots) -> str:
    path = root / book_id / "understand.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    used = {
        (item.page, item.panel)
        for shot in shot_book.shots
        for item in shot.panels
    }
    unused = [
        f"{page['filename'][1:4]}.{panel['index']}"
        for page in content["pages"]
        for panel in page["panels"]
        if (page["filename"], panel["index"]) not in used
    ]
    if not unused:
        return "0 panels"
    return f"{len(unused)} panels " + " ".join(unused)


if __name__ == "__main__":
    raise SystemExit(main())
