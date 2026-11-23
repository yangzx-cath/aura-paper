"""Small helpers shared across the project."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def extract_json(text: str) -> dict:
    """Return the first JSON object found in text."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found in text")

    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        at = start + exc.pos
        near = text[max(start, at - 30) : at + 30]
        raise ValueError(f"invalid JSON: {exc.msg} near {near!r}") from exc

    return obj


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
