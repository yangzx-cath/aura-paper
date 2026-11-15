"""Reuse model results keyed by a content fingerprint."""

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


class Cache:
    """Store results per namespace, keyed by a content fingerprint."""

    root: Path
    enabled: bool

    def __init__(self, root: str | Path, *, enabled: bool = True) -> None:
        raise NotImplementedError("Cache.__init__")

    def path(self, ns: str, name: str, key: str) -> Path:
        """Return the file that would hold this entry."""
        raise NotImplementedError("Cache.path")

    def has(self, ns: str, name: str, key: str) -> bool:
        """Return True when the entry exists on disk."""
        raise NotImplementedError("Cache.has")

    def load_json(self, ns: str, name: str, key: str) -> dict | None:
        """Return the stored entry, or None when it is missing or broken."""
        raise NotImplementedError("Cache.load_json")

    def save_json(self, ns: str, name: str, key: str, data: dict) -> Path:
        """Write the entry and return its path."""
        raise NotImplementedError("Cache.save_json")

    def clear(self, ns: str | None = None) -> int:
        """Remove a namespace or the whole cache, returning file count."""
        raise NotImplementedError("Cache.clear")

    def stats(self) -> dict[str, int]:
        """Return the running hit and miss counters."""
        raise NotImplementedError("Cache.stats")


_SEPARATOR = "\x1f"


def fingerprint(*parts: Any) -> str:
    """Return a 16 character fingerprint of the given parts."""
    payload = _SEPARATOR.join(_canonical(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# Render one input as text, keeping type and ignoring key order.
def _canonical(part: Any) -> str:
    if isinstance(part, bytes):
        return json.dumps({"bytes": part.hex()})
    if isinstance(part, Path):
        part = str(part)
    return json.dumps(part, sort_keys=True, ensure_ascii=False, default=str)


_CHUNK_SIZE = 1 << 20


def file_fingerprint(path: str | Path) -> str:
    """Return a 16 character fingerprint of a file's contents."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def recall_json(
    cache: Cache,
    ns: str,
    name: str,
    key: str,
    compute: Callable[[], dict],
) -> dict:
    """Return the cached entry, or compute and store it."""
    raise NotImplementedError("recall_json")
