"""Resolve paths and read local environment settings."""

import os
from pathlib import Path

CACHE_DIR_ENV = "AURA_CACHE_DIR"
OUT_DIR_ENV = "AURA_OUT_DIR"
BOOKS_DIR_ENV = "AURA_BOOKS_DIR"
APP_NAME = "aura-paper"


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


def cache_root() -> Path:
    """Return the cache root without creating it."""
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override).expanduser()

    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base.expanduser() / APP_NAME


def out_root() -> Path:
    """Return the output root without creating it."""
    override = os.environ.get(OUT_DIR_ENV)
    if override:
        return Path(override).expanduser()

    return Path.cwd() / "out"


def books_dir() -> Path:
    """Return the book library root without creating it."""
    override = os.environ.get(BOOKS_DIR_ENV)
    if override:
        return Path(override).expanduser()

    return Path.cwd() / "data" / "books"
