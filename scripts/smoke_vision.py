"""Manual smoke test for the vision client.

Endpoint and model have defaults below; the API key is read from the
environment or from a local .env file.

Usage:
    export VISION_API_KEY=sk-xxx
    python scripts/smoke_vision.py [image] [single|spread] [--raw]
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from book import PageImage  # noqa: E402
from prompts import page_prompt  # noqa: E402
from understand import understand_page  # noqa: E402
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
    parser = argparse.ArgumentParser(description="Smoke test the vision path.")
    parser.add_argument("image", nargs="?", default=str(DEFAULT_IMAGE))
    parser.add_argument("kind", nargs="?", default="single")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the raw reply instead of parsed content",
    )
    args = parser.parse_args()

    load_env(ENV_FILE)

    image = Path(args.image)
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
    print(f"kind: {args.kind}")

    if not client.api_key:
        print("VISION_API_KEY is not set", file=sys.stderr)
        return 2

    started = time.perf_counter()
    if args.raw:
        code = run_raw(client, image, args.kind)
    else:
        code = run_understand(client, image, args.kind)
    print(f"elapsed: {time.perf_counter() - started:.2f}s")
    return code


def run_raw(client: VisionClient, image: Path, kind: str) -> int:
    try:
        reply = client.analyze(page_prompt(kind), image)
    except VisionError as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(f"reply: {reply[:500]}")
    return 0


def run_understand(client: VisionClient, image: Path, kind: str) -> int:
    page = PageImage(
        index=0,
        filename=image.name,
        path=str(image),
        kind=kind,
    )
    content = understand_page(page, client)

    print(f"error: {content.error}")
    print(f"page_text: {content.page_text}")
    print(f"description: {content.description}")
    print(f"mood: {content.mood}")

    if content.error:
        print("hint: rerun with --raw to see the raw reply")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
