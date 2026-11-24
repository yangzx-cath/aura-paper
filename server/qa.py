"""Store the voice recordings a reader sends from the page."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from re import fullmatch

from fastapi import APIRouter, HTTPException, Request

ROOT = Path(__file__).resolve().parent.parent / "data" / "recordings"

# One query is a few seconds, so 20MB is far above any real recording.
MAX_BYTES = 20 * 1024 * 1024

# The browser names the container, so the file suffix follows it.
SUFFIXES = {
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
}

# Book ids are assigned by the library: B001, C01 and so on.
BOOK_ID = r"[A-Z]\d{2,3}"

router = APIRouter(prefix="/api", tags=["qa"])


@router.post("/qa/audio")
async def audio(request: Request, book: str = "") -> dict:
    """Store one recording under data/recordings/<book>/."""
    suffix = SUFFIXES.get(_kind(request))
    if suffix is None:
        raise HTTPException(status_code=415, detail="不支持的录音格式")
    if fullmatch(BOOK_ID, book) is None:
        raise HTTPException(status_code=400, detail="书籍编号不对")

    length = int(request.headers.get("content-length") or 0)
    if length > MAX_BYTES:
        raise HTTPException(status_code=413, detail="录音太大")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="录音是空的")

    folder = ROOT / book
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_stamp()}{suffix}"
    path.write_bytes(body)
    return {"file": path.relative_to(ROOT).as_posix(), "bytes": len(body)}


# The mime type before any codec parameter decides the container.
def _kind(request: Request) -> str:
    header = request.headers.get("content-type", "")
    return header.split(";")[0].strip().lower()


# Names sort by time and never repeat within one microsecond.
def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
