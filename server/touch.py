"""Name the thing a child taps on a video frame."""

from __future__ import annotations

import logging
import tempfile
from base64 import b64decode
from pathlib import Path
from re import fullmatch

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from aura_paper.clients.llm import LLMClient, LLMError
from aura_paper.clients.reply import extract_json
from aura_paper.config import cache_root
from aura_paper.prompts import touch_prompt
from aura_paper.schema.publish import PublishTopic
from aura_paper.store.books import read_publish
from aura_paper.store.cache import Cache, file_fingerprint, fingerprint

# Book ids are assigned by the library: B001, C01 and so on.
BOOK_ID = r"[A-Z]\d{2,3}"

# A 720p frame is under 300KB as JPEG, so this is already generous.
MAX_IMAGE = 4 * 1024 * 1024

# Cache namespace for one answered tap.
CACHE_NS = "touch"

# What to say when the tap lands on something the book has nothing about.
NOTHING = "这里没有特别要说的事情"

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api", tags=["touch"])


class Touch(BaseModel):
    """One tap on one frame of one book."""

    book: str = ""
    time: float = 0.0
    x: float = 0.0
    y: float = 0.0
    image: str = ""


@router.post("/touch")
async def touch(body: Touch) -> dict:
    """Pick the topic the tap landed on and return its box."""
    if fullmatch(BOOK_ID, body.book) is None:
        raise HTTPException(status_code=400, detail="书籍编号不对")

    release = read_publish(body.book)
    if release is None:
        raise HTTPException(status_code=404, detail="这本书还没发布")

    topics = _topics(release)
    if not topics:
        return {"topic": None, "box": [], "note": NOTHING}

    page = _page_at(release.get("pages") or [], body.time)
    candidates = [topic for topic in topics if page in topic.pages] or topics
    image = _image(body.image)

    client = LLMClient.from_env(effort="none")
    if client.missing_settings():
        raise HTTPException(status_code=503, detail="识别模型未配置")

    prompt = touch_prompt(candidates, page, body.x, body.y)
    try:
        answer = await run_in_threadpool(
            _ask, client, prompt, image, body.book
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError:
        # A reply that is not JSON tells the child nothing, not a wrong thing.
        answer = {}

    logger.info(
        "touch %s page %s at %.2f,%.2f -> %s",
        body.book,
        page,
        body.x,
        body.y,
        answer.get("id") or "none",
    )
    return _result(answer, candidates)


# Write the frame to a temp file, ask the model, and reuse an earlier answer.
def _ask(client: LLMClient, prompt: str, data: bytes, book: str) -> dict:
    cache = Cache(cache_root())
    with tempfile.NamedTemporaryFile(suffix=".jpg") as frame:
        frame.write(data)
        frame.flush()
        path = Path(frame.name)
        key = fingerprint(file_fingerprint(path), prompt, client.model)
        entry = cache.load_json(CACHE_NS, book, key)
        if entry is None:
            entry = extract_json(client.chat(prompt, images=[path]))
            cache.save_json(CACHE_NS, book, key, entry)
    return entry


# Read the topics a release carries, skipping the ones without a name.
def _topics(release: dict) -> list[PublishTopic]:
    rows = release.get("topics") or []
    return [
        PublishTopic.from_dict(row)
        for row in rows
        if isinstance(row, dict) and row.get("name")
    ]


# The page playing at this second; 0 when the film has not started.
def _page_at(pages: list[dict], at: float) -> int:
    page = 0
    for row in pages:
        if float(row.get("start") or 0) <= at + 0.01:
            page = int(row.get("page") or 0)
    return page


# Accept a data URL or bare base64, and refuse anything that is not a JPEG.
def _image(text: str) -> bytes:
    body = str(text or "")
    if "," in body:
        body = body.split(",", 1)[1]
    try:
        data = b64decode(body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="图片解不开") from exc
    if not data or len(data) > MAX_IMAGE:
        raise HTTPException(status_code=400, detail="图片大小不合适")
    if not data.startswith(b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="只接受 JPEG")
    return data


# Keep the id when it names a candidate, and the box when it is in range.
def _result(answer: dict, candidates: list[PublishTopic]) -> dict:
    topic = _find(str(answer.get("id") or ""), candidates)
    if topic is None:
        return {"topic": None, "box": [], "note": NOTHING}
    return {
        "topic": {
            "id": topic.id,
            "name": topic.name,
            "kind": topic.kind,
            "intro": topic.intro,
        },
        "box": _box(answer.get("box")),
        "note": "",
    }


# The model may answer with the id, the name or another name it knows.
def _find(key: str, candidates: list[PublishTopic]) -> PublishTopic | None:
    word = key.strip().lower()
    if not word:
        return None
    for topic in candidates:
        names = [topic.id, topic.name, *topic.aliases]
        if word in {name.strip().lower() for name in names if name}:
            return topic
    return None


# A box is four numbers in 0..1; anything else is dropped.
def _box(value: object) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        return []
    numbers = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return []
        numbers.append(round(min(1.0, max(0.0, float(item))), 4))
    left, top, right, bottom = numbers
    if right <= left or bottom <= top:
        return []
    return numbers
