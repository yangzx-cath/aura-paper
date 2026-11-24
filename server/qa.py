"""Store the voice a reader sends and read PCM phrases as text."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from re import fullmatch

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from aura_paper.clients.asr import ASRClient, ASRError

ROOT = Path(__file__).resolve().parent.parent / "data" / "recordings"

# One query is a few seconds, so 20MB is far above any real recording.
MAX_BYTES = 20 * 1024 * 1024

# The browser names the container, so the file suffix follows it.
SUFFIXES = {
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/pcm": ".pcm",
}

# Only raw PCM goes straight to the endpoint, which takes no container.
PCM_SUFFIX = ".pcm"

# Words a reader is likely to say, used to bias the endpoint.
HOTWORDS = ("暂停", "播放", "继续", "开始")

# Book ids are assigned by the library: B001, C01 and so on.
BOOK_ID = r"[A-Z]\d{2,3}"

router = APIRouter(prefix="/api", tags=["qa"])


@router.post("/qa/audio")
async def audio(request: Request, book: str = "") -> dict:
    """Store one recording and return the text of a PCM phrase."""
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

    text = await _hear(body) if suffix == PCM_SUFFIX else ""
    name = path.relative_to(ROOT).as_posix()
    return {"file": name, "bytes": len(body), "text": text}


# Turn one phrase into text, off the event loop and with retries kept.
async def _hear(pcm: bytes) -> str:
    client = ASRClient.from_env()
    if client.missing_settings():
        raise HTTPException(status_code=503, detail="语音识别未配置")
    try:
        hearing = await run_in_threadpool(
            client.transcribe, pcm, hotwords=HOTWORDS
        )
    except ASRError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return hearing.text


# The mime type before any codec parameter decides the container.
def _kind(request: Request) -> str:
    header = request.headers.get("content-type", "")
    return header.split(";")[0].strip().lower()


# Names sort by time and never repeat within one microsecond.
def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
