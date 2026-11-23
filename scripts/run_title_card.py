"""Speak the cover title and build the title card of one book.

Reads out/<book>/understand.json for the title and the cover, voice.json
for the narrator's voice, and writes out/<book>/shots/title_card.mp4.

Usage:
    python scripts/run_title_card.py C01 --size 752x560
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.clients.tts import TTSClient, TTSError
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.media import ffmpeg
from aura_paper.stages.compose import (
    TITLE_LEAD_MS,
    TITLE_SPEED,
    TITLE_TAIL_MS,
    title_card,
)
from aura_paper.store.cache import Cache

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the title card.")
    parser.add_argument("book", help="book id produced by run_understand.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--size",
        default="",
        metavar="WxH",
        help="frame size, taken from the first clip when left out",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=TITLE_SPEED,
        help=f"speech speed (default={TITLE_SPEED})",
    )
    parser.add_argument(
        "--lead",
        type=int,
        default=TITLE_LEAD_MS,
        metavar="MS",
        help=f"silence before the title (default={TITLE_LEAD_MS})",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=TITLE_TAIL_MS,
        metavar="MS",
        help=f"silence after the title (default={TITLE_TAIL_MS})",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    directory = root / args.book
    if not (directory / "understand.json").is_file():
        print(f"missing {directory / 'understand.json'}", file=sys.stderr)
        print("run scripts/run_understand.py first", file=sys.stderr)
        return 2

    missing = ffmpeg.missing_tools()
    if missing:
        print("missing tools: " + ", ".join(missing), file=sys.stderr)
        return 2

    tts = TTSClient.from_env()
    missing = tts.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    size = _clip_size(directory)
    if args.size:
        try:
            size = _parse_size(args.size)
        except ValueError:
            print(f"bad size: {args.size}", file=sys.stderr)
            return 2
    if size is None:
        print(
            "pass --size WxH, there is no clip to take it from",
            file=sys.stderr,
        )
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)

    print(f"book     {args.book}")
    print(f"root     {root}")
    print(f"size     {size[0]}x{size[1]}")
    print(f"speed    {args.speed}")
    print(f"lead     {args.lead}ms  tail {args.tail}ms")
    print()
    print("Building the title card", flush=True)

    started = time.perf_counter()
    try:
        card = title_card(
            args.book,
            tts=tts,
            size=size,
            root=root,
            cache=cache,
            speed=args.speed,
            lead_ms=args.lead,
            tail_ms=args.tail,
        )
    except (TTSError, ffmpeg.FFmpegError, ValueError) as exc:
        print(f"error    {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    info = ffmpeg.probe(directory / card)
    print(f"card     {card}  {info.duration_ms / 1000:.1f}s")
    print(f"total    {elapsed:.1f}s")
    return 0


# Read a frame size like 752x560.
def _parse_size(text: str) -> tuple[int, int]:
    width, _, height = text.lower().partition("x")
    return int(width), int(height)


# Take the frame size from the first clip the render stage wrote.
def _clip_size(directory: Path) -> tuple[int, int] | None:
    clips = sorted((directory / "clips").glob("*.mp4"))
    if not clips:
        return None
    info = ffmpeg.probe(clips[0])
    return info.width, info.height


if __name__ == "__main__":
    raise SystemExit(main())
