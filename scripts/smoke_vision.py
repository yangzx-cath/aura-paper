"""Manual smoke test for the vision client.

Endpoint and model have defaults below; the API key is read from the
environment or from a local .env file.

Usage:
    export VISION_API_KEY=sk-xxx
    python scripts/smoke_vision.py [image] [single|spread]
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from prompts import page_prompt  # noqa: E402
from vision import VisionClient, VisionError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
DEFAULT_IMAGE = ROOT / "data" / "chicken_and_sunflower" / "02.jpg"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.8-max"


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env(ENV_FILE)

    image = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    kind = sys.argv[2] if len(sys.argv) > 2 else "single"
    if not image.is_file():
        print(f"image not found: {image}", file=sys.stderr)
        return 2

    client = VisionClient(
        base_url=os.environ.get("VISION_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.environ.get("VISION_API_KEY", ""),
        model=os.environ.get("VISION_MODEL", DEFAULT_MODEL),
        timeout=float(os.environ.get("VISION_TIMEOUT", "120")),
    )
    print(f"client: {client}")
    print(f"kind: {kind}")

    if not client.api_key:
        print("VISION_API_KEY is not set", file=sys.stderr)
        return 2

    started = time.perf_counter()
    try:
        reply = client.analyze(page_prompt(kind), image)
    except VisionError as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - started
    print(f"elapsed: {elapsed:.2f}s")
    print(f"reply: {reply[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
