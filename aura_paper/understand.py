"""
Interpret page images into structured content.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .book import Book, Page
from .cache import Cache, file_fingerprint, fingerprint
from .llm import LLMClient, LLMError
from .output import write_json
from .prompts import cover_prompt, page_prompt
from .utils import extract_json, now_iso


@dataclass
class CoverContent:
    """The book details read from the cover."""

    title: str = ""
    author: str = ""
    illustrator: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this cover."""
        return {
            "title": self.title,
            "author": self.author,
            "illustrator": self.illustrator,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CoverContent:
        """Build a cover from its external JSON shape."""
        return cls(
            title=str(data.get("title") or ""),
            author=str(data.get("author") or ""),
            illustrator=str(data.get("illustrator") or ""),
        )


@dataclass
class PageContent:
    """Structured content of one page."""

    index: int
    filename: str
    kind: str = "portrait"
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
            kind=str(data.get("kind") or "portrait"),
            page_text=str(data.get("page_text") or ""),
            footer=str(data.get("footer") or ""),
            description=str(data.get("description") or ""),
            mood=str(data.get("mood") or ""),
            mood_detail=str(data.get("mood_detail") or ""),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


@dataclass
class BookContent:
    """Structured content of a whole book."""

    id: str
    source: str
    cover: CoverContent = field(default_factory=CoverContent)
    pages: list[PageContent] = field(default_factory=list)

    @property
    def title(self) -> str:
        """Return the title printed on the cover."""
        return self.cover.title

    @property
    def page_count(self) -> int:
        """Return the number of pages, the cover included."""
        return len(self.pages)

    @property
    def failed_count(self) -> int:
        """Return how many pages failed, the cover included."""
        return sum(1 for page in self.pages if page.error)

    @property
    def cover_page(self) -> PageContent | None:
        """Return the first page, which is the cover."""
        return self.pages[0] if self.pages else None

    @property
    def story_pages(self) -> list[PageContent]:
        """Return the pages after the cover, which carry the story."""
        return self.pages[1:]

    @property
    def language(self) -> str:
        """Return the language printed on the pages, so narration uses it."""
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
            "cover": self.cover.to_dict(),
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookContent:
        """Build a book from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            source=str(data.get("source") or ""),
            cover=CoverContent.from_dict(data.get("cover") or {}),
            pages=[
                PageContent.from_dict(page) for page in data.get("pages") or []
            ],
        )


def understand_cover(
    page: Page,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    ns: str = "understand",
    directory: str = "",
) -> tuple[PageContent, CoverContent]:
    """Read the cover and return its page content plus the book metadata."""
    kind = "landscape" if page.width > page.height else "portrait"
    content = PageContent(
        index=page.index,
        filename=page.filename,
        kind=kind,
        model=client.model,
    )
    cover = CoverContent()
    prompt = cover_prompt(kind)
    path = Path(directory) / page.filename

    if cache is None:
        return _analyze_cover(content, cover, client, prompt, path)

    key = fingerprint(
        file_fingerprint(path),
        prompt,
        *client.signature,
    )

    entry = cache.load_json(ns, "cover", key)
    if entry is not None:
        _apply_cover(content, cover, entry)
        return content, cover

    content, cover = _analyze_cover(content, cover, client, prompt, path)
    # Errors are never cached, so a failed cover is retried next run.
    if not content.error:
        cache.save_json(ns, "cover", key, _cover_fields(content, cover))
    return content, cover


# Call the model for the cover and fill the page content and book details.
def _analyze_cover(
    content: PageContent,
    cover: CoverContent,
    client: LLMClient,
    prompt: str,
    path: Path,
) -> tuple[PageContent, CoverContent]:
    try:
        reply = client.chat(prompt, image_path=path)
        fields = extract_json(reply)
    except (LLMError, ValueError) as exc:
        content.error = str(exc)
        return content, cover

    _apply_cover(content, cover, fields)
    if not cover.title and not content.description:
        content.error = "model returned no content"
    return content, cover


# Copy the cover fields, turning missing or null values into empty strings.
def _apply_cover(
    content: PageContent,
    cover: CoverContent,
    fields: dict,
) -> None:
    content.description = str(fields.get("description") or "")
    cover.title = str(fields.get("title") or "")
    cover.author = str(fields.get("author") or "")
    cover.illustrator = str(fields.get("illustrator") or "")


# Keep only what the model produced, so the cache holds no page identity.
def _cover_fields(content: PageContent, cover: CoverContent) -> dict:
    return {
        "title": cover.title,
        "author": cover.author,
        "illustrator": cover.illustrator,
        "description": content.description,
    }


def understand_page(
    page: Page,
    client: LLMClient,
    *,
    cache: Cache | None = None,
    ns: str = "understand",
    directory: str = "",
) -> PageContent:
    """Read one page and return its structured content."""
    kind = "landscape" if page.width > page.height else "portrait"
    content = PageContent(
        index=page.index,
        filename=page.filename,
        kind=kind,
        model=client.model,
    )
    prompt = page_prompt(kind)
    path = Path(directory) / page.filename

    if cache is None:
        return _analyze_page(content, client, prompt, path)

    name = f"page_{page.index:02d}"
    key = fingerprint(
        file_fingerprint(path),
        prompt,
        *client.signature,
    )

    entry = cache.load_json(ns, name, key)
    if entry is not None:
        _apply_fields(content, entry)
        return content

    content = _analyze_page(content, client, prompt, path)
    # Errors are never cached, so a failed page is retried next run.
    if not content.error:
        cache.save_json(ns, name, key, _page_fields(content))
    return content


# Call the model for one page and fill the result fields.
def _analyze_page(
    content: PageContent,
    client: LLMClient,
    prompt: str,
    path: Path,
) -> PageContent:
    try:
        reply = client.chat(prompt, image_path=path)
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
    content.page_text = str(fields.get("page_text") or "")
    content.footer = str(fields.get("footer") or "")
    content.description = str(fields.get("description") or "")
    content.mood = str(fields.get("mood") or "")
    content.mood_detail = str(fields.get("mood_detail") or "")


# Keep only what the model produced, so page identity stays current.
def _page_fields(content: PageContent) -> dict:
    return {
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
    on_page: Callable[[Page, PageContent, float], None] | None = None,
) -> BookContent:
    """Read every page of a book and collect the results."""
    assert workers >= 1

    content = BookContent(
        id=book.id,
        source=book.directory,
    )

    ns = f"understand/{book.id}"
    pages = book.pages

    # A bad page only sets its error, so other pages keep going.
    def run(page: Page) -> PageContent:
        started = time.perf_counter()
        result = understand_page(
            page,
            client,
            cache=cache,
            ns=ns,
            directory=book.directory,
        )
        if on_page is not None:
            on_page(page, result, time.perf_counter() - started)
        return result

    def run_cover(page: Page) -> tuple[PageContent, CoverContent]:
        started = time.perf_counter()
        result, cover = understand_cover(
            page,
            client,
            cache=cache,
            ns=ns,
            directory=book.directory,
        )
        if on_page is not None:
            on_page(page, result, time.perf_counter() - started)
        return result, cover

    if not pages:
        return content

    cover_page = pages[0]
    story = pages[1:]

    if workers == 1:
        cover_content, content.cover = run_cover(cover_page)
        results = [cover_content] + [run(page) for page in story]
    else:
        # The cover feeds no page, so it runs beside them instead of first.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            cover_future = pool.submit(run_cover, cover_page)
            # pool.map() keeps the input order, so pages stay in book order.
            story_results = list(pool.map(run, story))
            cover_content, content.cover = cover_future.result()
        results = [cover_content] + story_results

    content.pages = results
    return content


def save_content(
    content: BookContent,
    root: str | Path | None = None,
) -> Path:
    """Write the book content to <root>/<book_id>/content.json."""
    return write_json(content.id, "content", content.to_dict(), root)
