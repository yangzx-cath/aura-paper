"""Reuse model results keyed by a content fingerprint."""

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


def digest(*parts: Any) -> str:
    """Return a 16 character fingerprint of the given parts."""
    raise NotImplementedError("digest")


def file_digest(path: str | Path) -> str:
    """Return a 16 character fingerprint of a file's contents."""
    raise NotImplementedError("file_digest")


def recall_json(
    cache: Cache,
    ns: str,
    name: str,
    key: str,
    compute: Callable[[], dict],
) -> dict:
    """Return the cached entry, or compute and store it."""
    raise NotImplementedError("recall_json")
