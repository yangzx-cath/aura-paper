"""Stage artifacts on disk."""

import json
from pathlib import Path

from ..config import output_root


def write_json(
    book_id: str,
    name: str,
    data: dict,
    root: str | Path | None = None,
) -> Path:
    """Write one artifact and return its path."""
    base = Path(root) if root is not None else output_root()
    path = base / book_id / f"{name}.json"

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
    return path
