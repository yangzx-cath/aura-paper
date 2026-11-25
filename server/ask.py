"""Answer one spoken question about a published book."""

from __future__ import annotations

import json
from base64 import b64encode
from re import fullmatch

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from aura_paper.clients.llm import LLMClient, LLMError
from aura_paper.clients.tts import TTSClient, TTSError
from aura_paper.schema.voice import narrator_for
from aura_paper.store.books import read_publish

# 页面表里每页取多少字，防止个别页把提示词撑大。
DESC_LIMIT = 80
TEXT_LIMIT = 40

# Book ids are assigned by the library: B001, C01 and so on.
BOOK_ID = r"[A-Z]\d{2,3}"

router = APIRouter(prefix="/api", tags=["ask"])


class Ask(BaseModel):
    """One question about one book."""

    book: str = ""
    query: str = ""
    page: int = 0


@router.post("/ask")
async def ask(body: Ask) -> dict:
    """Pick the page a question is about, or answer it from the book."""
    if fullmatch(BOOK_ID, body.book) is None:
        raise HTTPException(status_code=400, detail="书籍编号不对")
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="问题为空")

    release = read_publish(body.book)
    if release is None:
        raise HTTPException(status_code=404, detail="这本书还没发布")
    pages = release.get("pages") or []
    if not pages:
        raise HTTPException(status_code=404, detail="发布清单里没有页面")

    client = LLMClient.from_env(effort="none")
    if client.missing_settings():
        raise HTTPException(status_code=503, detail="问答模型未配置")

    prompt = _prompt(release, pages, query, body.page)
    try:
        reply = await run_in_threadpool(client.chat, prompt, max_tokens=300)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = _result(reply, len(pages))
    if result.get("kind") == "answer":
        result["audio"] = await _speak(result["answer"], release)
    return result


# 回答转成一段 WAV 交给页面播放；合不出来就只回文字。
async def _speak(text: str, release: dict) -> str:
    client = TTSClient.from_env()
    if client.missing_settings():
        return ""
    voice = narrator_for(str(release.get("language") or "zh"))
    try:
        speech = await run_in_threadpool(client.synthesize, text, voice=voice)
    except TTSError:
        return ""
    return b64encode(speech.data).decode("ascii")


# 把整本书压成一份页面表，让模型自己判断问题落在哪一页。
def _prompt(
    release: dict,
    pages: list[dict],
    query: str,
    page: int,
) -> str:
    lines = ["你是一名儿童绘本讲解助手。"]
    title = release.get("title") or "这本绘本"
    lines.append(f"书名：{title}")
    names = [
        str(member.get("name") or "") for member in release.get("cast") or []
    ]
    names = [name for name in names if name]
    if names:
        lines.append("人物：" + "、".join(names))

    lines.append("")
    lines.append("页面内容：")
    for row in pages:
        seen = _clip(row.get("desc"), DESC_LIMIT)
        said = _clip(row.get("text"), TEXT_LIMIT)
        number = int(row.get("page") or 0) + 1
        lines.append(f"{number}. 画面：{seen} 台词：{said}")

    lines.extend(
        [
            "",
            "规则：",
            "- 用户在找某一页画面时，返回 " '{"kind":"find","page":页码}。',
            "- 用户在问发生了什么或为什么时，返回 "
            '{"kind":"answer","answer":"1-2 句","page":页码}。',
            "- answer 只能依据上面的内容，不能编造。",
            '- 都回答不了就返回 {"kind":"none"}。',
            "- 只输出 JSON，页码是 1 起的数字。",
        ]
    )
    if page:
        lines.append(f"- 当前在第 {page + 1} 页，往后找优先。")
    lines.append("")
    lines.append(f"用户的话：{query}")
    return "\n".join(lines)


# 摘要长度按字数截断，换行压成空格。
def _clip(text: object, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat[:limit]


# 校验模型的 JSON：页码必须在书里，种类只认三种。
def _result(reply: str, total: int) -> dict:
    data = _json(reply)
    kind = str(data.get("kind") or "").strip().lower()
    page = _page(data.get("page"), total)
    if kind == "find" and page is not None:
        why = str(data.get("why") or "").strip()
        return {"kind": "find", "page": page, "why": why}
    if kind == "answer":
        answer = str(data.get("answer") or "").strip()
        if answer:
            return {"kind": "answer", "answer": answer, "page": page}
    return {"kind": "none"}


# 1 起的页码换回 0 起，越界算没找到。
def _page(value: object, total: int) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if 1 <= number <= total:
        return number - 1
    return None


# 模型偶尔带上代码块或前后废话，这里只取第一段 JSON。
def _json(reply: str) -> dict:
    text = reply.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
