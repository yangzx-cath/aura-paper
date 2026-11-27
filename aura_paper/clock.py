"""Timestamps in one format across the project."""

from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
