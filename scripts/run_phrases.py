"""Synthesize the canned replies the reader plays between answers."""

import sys
from pathlib import Path

from aura_paper.clients.tts import TTSClient, TTSError
from aura_paper.config import load_env
from aura_paper.schema.voice import narrator_for

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "resources" / "voice"

# 找到、答不上来、没听清、还在看，四种固定场合各配一句现成的话。
PHRASES = {
    "found": "哦，找到啦！",
    "unknown": "嗯，这个，我也不知道……",
    "unheard": "对不起，没有听清……",
    "think": "让我看看……",
}


def main() -> int:
    """Synthesize the named phrases, or all of them when none are named."""
    load_env(ROOT / ".env")
    names = sys.argv[1:] or list(PHRASES)
    unknown = [name for name in names if name not in PHRASES]
    if unknown:
        print("unknown phrase: " + ", ".join(unknown), file=sys.stderr)
        return 2

    client = TTSClient.from_env()
    missing = client.missing_settings()
    if missing:
        print("missing " + ", ".join(missing), file=sys.stderr)
        return 2

    TARGET.mkdir(parents=True, exist_ok=True)
    voice = narrator_for("zh")
    for name in names:
        try:
            speech = client.synthesize(PHRASES[name], voice=voice)
        except TTSError as exc:
            print(f"{name}: {exc}", file=sys.stderr)
            return 1
        path = speech.save(TARGET / f"{name}.wav")
        print(f"{name}  {speech.duration_ms} ms  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
