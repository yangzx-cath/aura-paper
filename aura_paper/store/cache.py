"""A file cache keyed by a content fingerprint."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any

# Fingerprint parts are joined by a character no path or text holds.
_SEPARATOR = "\x1f"

# Files are hashed a megabyte at a time.
_CHUNK_SIZE = 1 << 20


class Cache:
    """Store results per namespace, keyed by a content fingerprint."""

    root: Path
    enabled: bool
    _stats: dict[str, int]
    _lock: Lock

    def __init__(self, root: str | Path, *, enabled: bool = True) -> None:
        self.root = Path(root).expanduser().resolve()
        self.enabled = enabled
        self._stats = {"hit": 0, "miss": 0}
        self._lock = Lock()

    def path(self, ns: str, name: str, key: str) -> Path:
        """Return the file that would hold this entry."""
        return self.root / ns / f"{name}-{key}.json"

    def file_path(self, ns: str, key: str, suffix: str) -> Path:
        """Return the file that would hold an entry that is not JSON."""
        return self.root / ns / f"{key}{suffix}"

    def has(self, ns: str, name: str, key: str) -> bool:
        """Return True when the entry exists on disk."""
        return self.enabled and self.path(ns, name, key).is_file()

    def load_json(self, ns: str, name: str, key: str) -> dict | None:
        """Return the stored entry, or None when it is missing or broken."""
        if not self.enabled:
            return None

        try:
            text = self.path(ns, name, key).read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError):
            self._count("miss")
            return None

        if not isinstance(data, dict):
            self._count("miss")
            return None

        self._count("hit")
        return data

    # Add one to a counter without losing increments from other threads.
    def _count(self, key: str) -> None:
        with self._lock:
            self._stats[key] += 1

    def save_json(self, ns: str, name: str, key: str, data: dict) -> Path:
        """Write the entry and return its path."""
        path = self.path(ns, name, key)
        if not self.enabled:
            return path

        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file first so a crash cannot leave half a JSON.
        fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(temp_name, path)
        finally:
            Path(temp_name).unlink(missing_ok=True)
        return path

    def clear(self, ns: str | None = None) -> int:
        """Remove a namespace or the whole cache, returning file count."""
        target = self.root if ns is None else self.root / ns
        if not target.is_dir():
            return 0

        count = sum(1 for p in target.rglob("*") if p.is_file())
        shutil.rmtree(target)
        return count

    def stats(self) -> dict[str, int]:
        """Return the running hit and miss counters."""
        with self._lock:
            return dict(self._stats)


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


def file_fingerprint(path: str | Path) -> str:
    """Return a 16 character fingerprint of a file's contents."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]
