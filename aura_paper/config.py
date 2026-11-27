"""Resolve paths and read local environment settings."""

import os
from pathlib import Path

STORAGE_ENV = "AURA_STORAGE"

BOOKS_DIR_ENV = "AURA_BOOKS_DIR"
CACHE_DIR_ENV = "AURA_CACHE_DIR"
OUTPUT_DIR_ENV = "AURA_OUTPUT_DIR"


def load_env(path: str | Path | None = None) -> None:
    """Load a .env file into os.environ, keeping existing values."""
    env_path = Path(path) if path is not None else Path.cwd() / ".env"
    if not env_path.is_file():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def storage_root() -> Path:
    """Return the root of the runtime data."""
    override = os.environ.get(STORAGE_ENV)
    if override:
        return Path(override).expanduser()

    return Path.cwd() / "storage"


def books_dir() -> Path:
    """Return the book library root."""
    return _under(BOOKS_DIR_ENV, "books")


def cache_root() -> Path:
    """Return the cache root."""
    return _under(CACHE_DIR_ENV, "cache")


def output_root() -> Path:
    """Return the output root."""
    return _under(OUTPUT_DIR_ENV, "output")


# One directory under the storage root, unless its own variable is set.
def _under(env: str, name: str) -> Path:
    override = os.environ.get(env)
    if override:
        return Path(override).expanduser()

    return storage_root() / name
