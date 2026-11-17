"""
Interpret page images into structured content.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .book import Book, PageImage
from .cache import Cache, file_fingerprint, fingerprint
from .llm import LLMClient, LLMError
from .output import write_json
from .prompts import page_prompt
from .utils import extract_json, now_iso

PAGE_ROLES = ("cover", "story", "end")


@dataclass
class PageContent:
    """Structured content of one page."""

    index: int
    filename: str
    kind: str = "single"
    role: str = "story"
    page_text: str = ""
    footer: str = ""
    description: str = ""
    mood: str = ""
    mood_detail: str = ""
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        return {
            "index": self.index,
            "filename": self.filename,
            "kind": self.kind,
            "role": self.role,
            "model": self.model,
            "generated_at": now_iso(),
            "page_text": self.page_text,
            "footer": self.footer,
            "description": self.description,
            "mood": self.mood,
            "mood_detail": self.mood_detail,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PageContent:
        """Build a page from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            filename=str(data.get("filename") or ""),
            kind=str(data.get("kind") or "single"),
            role=_role(data.get("role")),
            page_text=str(data.get("page_text") or ""),
            footer=str(data.get("footer") or ""),
            description=str(data.get("description") or ""),
            mood=str(data.get("mood") or ""),
            mood_detail=str(data.get("mood_detail") or ""),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


# Keep a page role inside the supported set, defaulting to a story page.
def _role(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in PAGE_ROLES else "story"


@dataclass
class BookContent:
    """Structured content of a whole book."""

    id: str
    title: str
    source: str
    pages: list[PageContent] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def failed_count(self) -> int:
        return sum(1 for page in self.pages if page.error)

    # Pages that carry the story, or every page when none is marked "story".
    @property
    def story_pages(self) -> list[PageContent]:
        pages = [page for page in self.pages if page.role == "story"]
        return pages or list(self.pages)

    # Language the pages are printed in, so narration can stay in it.
    @property
    def language(self) -> str:
        text = "".join(page.page_text for page in self.pages)
        letters = [char for char in text if char.isalpha()]
        english = sum(1 for char in letters if char.isascii())
        return "英文" if english * 2 > len(letters) else "中文"

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "generated_at": now_iso(),
            "page_count": self.page_count,
            "failed_count": self.failed_count,
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookContent:
        """Build a book from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            source=str(data.get("source") or ""),
            pages=[
                PageContent.from_dict(page) for page in data.get("pages") or []
            ],
        )


def understand_page(
    page: PageImage,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    ns: str = "understand",
) -> PageContent:
    """Read one page and return its structured content."""
    content = PageContent(
        index=page.index,
        filename=page.filename,
        kind=page.kind,
        model=client.model,
    )
    prompt = page_prompt(page.kind)

    if cache is None:
        return _analyze_page(content, client, prompt, page)

    name = f"page_{page.index:02d}"
    key = fingerprint(
        file_fingerprint(page.path),
        prompt,
        client.model,
        client.reasoning_effort,
    )

    entry = cache.load_json(ns, name, key)
    if entry is not None:
        _apply_fields(content, entry)
        return content

    content = _analyze_page(content, client, prompt, page)
    # Errors are never cached, so a failed page is retried next run.
    if not content.error:
        cache.save_json(ns, name, key, _page_fields(content))
    return content


# Call the model for one page and fill the result fields.
def _analyze_page(
    content: PageContent,
    client: LLMClient,
    prompt: str,
    page: PageImage,
) -> PageContent:
    try:
        reply = client.chat(prompt, image_path=Path(page.path))
        fields = extract_json(reply)
    except (LLMError, ValueError) as exc:
        content.error = str(exc)
        return content

    _apply_fields(content, fields)
    if not content.page_text and not content.description:
        content.error = "model returned no content"
    return content


# Copy the model fields, turning missing or null values into empty strings.
def _apply_fields(content: PageContent, fields: dict) -> None:
    content.role = _role(fields.get("role"))
    content.page_text = str(fields.get("page_text") or "")
    content.footer = str(fields.get("footer") or "")
    content.description = str(fields.get("description") or "")
    content.mood = str(fields.get("mood") or "")
    content.mood_detail = str(fields.get("mood_detail") or "")


# Keep only what the model produced, so page identity stays current.
def _page_fields(content: PageContent) -> dict:
    return {
        "role": content.role,
        "page_text": content.page_text,
        "footer": content.footer,
        "description": content.description,
        "mood": content.mood,
        "mood_detail": content.mood_detail,
    }


def understand_book(
    book: Book,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    workers: int = 1,
    on_page: Callable[[PageImage, PageContent, float], None] | None = None,
) -> BookContent:
    """Read every page of a book and collect the results."""
    assert workers >= 1

    content = BookContent(
        id=book.id,
        title=book.title,
        source=book.source,
    )

    ns = f"understand/{book.id}"

    # A bad page only sets PageContent.error, so other pages keep going.
    def run(page: PageImage) -> PageContent:
        started = time.perf_counter()
        result = understand_page(page, client, cache=cache, ns=ns)
        if on_page is not None:
            on_page(page, result, time.perf_counter() - started)
        return result

    if workers == 1:
        results = [run(page) for page in book.pages]
    else:
        # pool.map() keeps the input order, so results stay in book order.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, book.pages))

    content.pages = results
    return content


def save_book(content: BookContent, root: str | Path | None = None) -> Path:
    """Write the book content to <root>/<book_id>/book.json."""
    return write_json(content.id, "book", content.to_dict(), root)
