"""Append-only record of what a reader said and tapped in a book."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import books_dir
from ..schema.time import now_iso

HISTORY_NAME = "history.jsonl"

# Keep the read short: the drawer shows the latest exchanges, not an archive.
READ_LIMIT = 100


def record(
    book_id: str,
    *,
    kind: str,
    text: str = "",
    answer: str = "",
    page: int = 0,
    time: float = 0.0,
    name: str = "",
    root: str | Path | None = None,
) -> dict:
    """Append one exchange to the book's history and return it."""
    entry = {
        "at": now_iso(),
        "kind": kind,
        "page": int(page or 0),
        "time": round(float(time or 0), 3),
        "name": str(name or ""),
        "text": str(text or ""),
        "answer": str(answer or ""),
    }
    path = _path(book_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read(
    book_id: str,
    *,
    limit: int = READ_LIMIT,
    root: str | Path | None = None,
) -> list[dict]:
    """Return the latest exchanges, newest first."""
    path = _path(book_id, root)
    if not path.is_file():
        return []

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows[-limit:][::-1]


# One book's history file, beside its source and release.
def _path(book_id: str, root: str | Path | None) -> Path:
    base = Path(root) if root is not None else books_dir()
    return base / book_id / HISTORY_NAME
