"""Speak every line of one book and measure how long each shot runs.

Reads out/<book>/shots.json, turns each line of a shot into audio, rests a
short gap between lines, and writes voice.json with the length of every
shot.

Usage:
    python scripts/run_voice.py C01 \\
        --voice 旁白=zh_female_xiaoxue_uranus_bigtts \\
        --voice c1=zh_female_mengyatou_uranus_bigtts
"""

import argparse
import sys
import time
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.clients.tts import TTSClient
from aura_paper.config import cache_root, load_env, out_root
from aura_paper.schema.voice import BookVoice, VoiceShot
from aura_paper.stages.voice import DEFAULT_GAP_MS, voice

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Speak every shot of a book.")
    parser.add_argument("book", help="book id produced by run_storyboard.py")
    parser.add_argument(
        "--root",
        default="",
        help="output root, default is the out root",
    )
    parser.add_argument(
        "--voice",
        action="append",
        default=[],
        metavar="说话人=音色",
        help="voice of one speaker, repeat for each speaker",
    )
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=DEFAULT_GAP_MS,
        help=f"rest between lines of one shot (default={DEFAULT_GAP_MS})",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the cache and do not write it",
    )
    args = parser.parse_args()

    load_env(ROOT / ".env")

    root = Path(args.root).expanduser() if args.root else out_root()
    shots_path = root / args.book / "shots.json"
    if not shots_path.is_file():
        print(f"missing {shots_path}", file=sys.stderr)
        print("run scripts/run_storyboard.py first", file=sys.stderr)
        return 2

    tts = TTSClient.from_env()
    missing = tts.missing_settings()
    if missing:
        print("missing config: " + ", ".join(missing), file=sys.stderr)
        return 2

    voices = _voices(args.voice)
    if not voices:
        print("give at least one --voice 说话人=音色", file=sys.stderr)
        return 2

    cache = Cache(cache_root(), enabled=not args.no_cache)

    print(f"book     {args.book}")
    print(f"resource {tts.resource_id}")
    print(f"root     {root}")
    print(f"cache    {cache.root}  enabled={cache.enabled}")
    print(f"gap      {args.gap_ms}ms")
    print()
    print("Speaking the lines", flush=True)

    started = time.perf_counter()
    result = voice(
        args.book,
        tts=tts,
        voices=voices,
        gap_ms=args.gap_ms,
        root=root,
        cache=cache,
    )
    elapsed = time.perf_counter() - started

    print()
    for shot in result.shots:
        print(_shot_line(shot))
    total = sum(shot.duration_ms for shot in result.shots)
    lines = sum(len(shot.lines) for shot in result.shots)
    print()
    print(f"lines    {lines}")
    print(f"silent   {_silent_line(result)}")
    print(f"audio    {total / 1000:.1f}s")
    print()
    print(f"total    {elapsed:.1f}s")
    print(f"output   {root / args.book / 'voice.json'}")
    if result.error:
        print(f"error    {result.error}", file=sys.stderr)
        return 1
    return 0


# Read the repeated speaker=voice arguments into a mapping.
def _voices(pairs: list[str]) -> dict[str, str]:
    voices = {}
    for pair in pairs:
        name, _, value = pair.partition("=")
        if name.strip() and value.strip():
            voices[name.strip()] = value.strip()
    return voices


# Print one shot with its length and line count.
def _shot_line(shot: VoiceShot) -> str:
    return (
        f"{shot.shot:5} {shot.duration_ms / 1000:5.1f}s  {len(shot.lines)} 句"
    )


# Name the shots that have no line to speak.
def _silent_line(result: BookVoice) -> str:
    silent = [shot.shot for shot in result.shots if not shot.lines]
    return " ".join(silent) or "none"


if __name__ == "__main__":
    raise SystemExit(main())
