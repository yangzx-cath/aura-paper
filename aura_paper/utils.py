"""Small helpers shared by the model clients."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

# Image suffixes accepted when loading a book.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

# Supported image suffixes and their MIME types.
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def data_url(path: Path) -> str:
    """Convert a local image file to a data URL."""
    mime = MIME_TYPES.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported image type: {path.suffix}")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def extract_json(text: str) -> dict:
    """Return the first JSON object found in text."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found in text")

    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc

    return obj


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
