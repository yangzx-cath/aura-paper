"""Store the voice a reader sends and read PCM phrases as text."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from re import fullmatch

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.concurrency import run_in_threadpool
from websockets.exceptions import WebSocketException

from aura_paper.clients.asr import ASRClient, ASRError, Hearing

ROOT = Path(__file__).resolve().parent.parent / "data" / "recordings"
OUT = Path(__file__).resolve().parent.parent / "out"

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

# 命令词永远在热词表里，其余按书从产物里取。
COMMANDS = ("暂停", "播放", "继续", "开始", "停止", "高亮", "重播")

# 流式接口的上下文约 100 token，按字数估算着用。
HOTWORD_LIMIT = 100

# Book ids are assigned by the library: B001, C01 and so on.
BOOK_ID = r"[A-Z]\d{2,3}"

router = APIRouter(prefix="/api", tags=["qa"])

# 识别结果打进 uvicorn 的日志，现场测时能直接看到。
logger = logging.getLogger("uvicorn.error")

# The voice socket keeps its own router, so it escapes the /api prefix.
socket_router = APIRouter()


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

    text = await _hear(body, book) if suffix == PCM_SUFFIX else ""
    name = path.relative_to(ROOT).as_posix()
    return {"file": name, "bytes": len(body), "text": text}


# Turn one phrase into text, off the event loop and with retries kept.
async def _hear(pcm: bytes, book: str) -> str:
    client = ASRClient.from_env()
    if client.missing_settings():
        raise HTTPException(status_code=503, detail="语音识别未配置")
    try:
        hearing = await run_in_threadpool(
            client.transcribe, pcm, hotwords=_hotwords(book)
        )
    except ASRError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return hearing.text


@socket_router.websocket("/ws/qa")
async def qa_socket(websocket: WebSocket) -> None:
    """Stream one spoken phrase in and send the text back as it grows."""
    await websocket.accept()
    book = websocket.query_params.get("book", "")
    if fullmatch(BOOK_ID, book) is None:
        await websocket.close(code=1008)
        return

    client = ASRClient.from_env()
    if client.missing_settings():
        await _fail(websocket, "语音识别未配置")
        return

    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    parts: list[bytes] = []
    reader = asyncio.create_task(_frames(websocket, queue, parts))
    try:
        hearing = await client.listen(
            _drain(queue),
            hotwords=_hotwords(book),
            on_text=lambda text: asyncio.create_task(_tell(websocket, text)),
        )
    except ASRError as exc:
        await _fail(websocket, str(exc))
        return
    except (OSError, WebSocketException):
        # 端点偶尔在握手时被重置，用已经收到的音频再试一次。
        if not parts:
            await _fail(websocket, "语音识别连接中断")
            return
        hearing = await _retry(client, websocket, book, parts)
        if hearing is None:
            return
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        reader.cancel()

    name = _save(book, b"".join(parts))
    logger.info(
        "asr %s %.2fs %r",
        book,
        hearing.duration_ms / 1000,
        hearing.text,
    )
    try:
        await websocket.send_json(
            {"type": "done", "text": hearing.text, "file": name}
        )
        await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass


# 用已经缓存的音频重开一次会话，成功后继续走落盘与回传。
async def _retry(
    client: ASRClient,
    websocket: WebSocket,
    book: str,
    parts: list[bytes],
) -> Hearing | None:
    try:
        return await client.listen(
            _again(parts),
            hotwords=_hotwords(book),
            on_text=lambda text: asyncio.create_task(_tell(websocket, text)),
        )
    except (ASRError, OSError, WebSocketException):
        await _fail(websocket, "语音识别连接中断")
        return None


# 把缓存好的切片再放一遍，给重试用。
async def _again(parts: list[bytes]) -> AsyncIterator[bytes]:
    for chunk in parts:
        yield chunk


# Turn the socket frames into the slices the endpoint expects.
async def _frames(
    websocket: WebSocket,
    queue: asyncio.Queue[bytes | None],
    parts: list[bytes],
) -> None:
    while True:
        try:
            message = await websocket.receive()
        except (WebSocketDisconnect, RuntimeError):
            break
        if message["type"] == "websocket.disconnect":
            break
        chunk = message.get("bytes")
        if chunk:
            parts.append(chunk)
            await queue.put(chunk)
            continue
        if _ended(message.get("text")):
            break
    await queue.put(None)


# Hand the client a plain stream of slices, closed by one None.
async def _drain(
    queue: asyncio.Queue[bytes | None],
) -> AsyncIterator[bytes]:
    while True:
        chunk = await queue.get()
        if chunk is None:
            return
        yield chunk


# The page says one word when the speaker stops.
def _ended(text: str | None) -> bool:
    if not text:
        return False
    try:
        return json.loads(text).get("type") == "end"
    except ValueError:
        return False


# Push the text so far; a socket the page already closed is not an error.
async def _tell(websocket: WebSocket, text: str) -> None:
    try:
        await websocket.send_json({"type": "text", "text": text})
    except (WebSocketDisconnect, RuntimeError):
        pass


async def _fail(websocket: WebSocket, detail: str) -> None:
    try:
        await websocket.send_json({"type": "error", "detail": detail})
        await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass


# Keep the phrase beside the other recordings of this book.
def _save(book: str, pcm: bytes) -> str:
    folder = ROOT / book
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_stamp()}.pcm"
    path.write_bytes(pcm)
    return path.relative_to(ROOT).as_posix()


# 命令词在前，然后角色、场景、地点，按优先级拼到额度用完。
def _hotwords(book: str) -> tuple[str, ...]:
    words = list(COMMANDS)
    words.extend(_names(OUT / book / "cast.json", "cast"))
    words.extend(_names(OUT / book / "scenes.json", "scenes"))
    words.extend(_names(OUT / book / "locations.json", "locations"))
    keep: list[str] = []
    total = 0
    for word in words:
        if not word or word in keep:
            continue
        if total + len(word) > HOTWORD_LIMIT:
            break
        keep.append(word)
        total += len(word)
    return tuple(keep)


# 从一个阶段产物里取名称，缺文件就当没有。
def _names(path: Path, key: str) -> list[str]:
    rows = _read(path).get(key)
    if not isinstance(rows, list):
        return []
    names = []
    for row in rows:
        if isinstance(row, dict):
            names.append(str(row.get("name") or "").strip())
    return names


# 读一份 JSON，缺失或坏掉都当空。
def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# The mime type before any codec parameter decides the container.
def _kind(request: Request) -> str:
    header = request.headers.get("content-type", "")
    return header.split(";")[0].strip().lower()


# Names sort by time and never repeat within one microsecond.
def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
