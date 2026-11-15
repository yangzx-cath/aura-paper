"""
Interpret page images into structured content.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .book import Book, PageImage
from .cache import Cache, file_fingerprint, fingerprint
from .config import out_root
from .prompts import page_prompt
from .vision import VisionClient, VisionError, extract_json


# Return the current UTC time in a sortable, timezone-aware form.
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class PageContent:
    """Structured content of one page."""

    index: int
    filename: str
    kind: str = "single"
    page_text: str = ""
    description: str = ""
    mood: str = ""
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        return {
            "index": self.index,
            "filename": self.filename,
            "kind": self.kind,
            "model": self.model,
            "generated_at": _now(),
            "page_text": self.page_text,
            "description": self.description,
            "mood": self.mood,
            "error": self.error,
        }


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

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "generated_at": _now(),
            "page_count": self.page_count,
            "failed_count": self.failed_count,
            "pages": [page.to_dict() for page in self.pages],
        }


def understand_page(
    page: PageImage,
    client: VisionClient,
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
    client: VisionClient,
    prompt: str,
    page: PageImage,
) -> PageContent:
    try:
        reply = client.analyze(prompt, Path(page.path))
        fields = extract_json(reply)
    except (VisionError, ValueError) as exc:
        content.error = str(exc)
        return content

    _apply_fields(content, fields)
    if not content.page_text and not content.description:
        content.error = "model returned no content"
    return content


# Copy the model fields, turning missing or null values into empty strings.
def _apply_fields(content: PageContent, fields: dict) -> None:
    content.page_text = fields.get("page_text", "") or ""
    content.description = fields.get("description", "") or ""
    content.mood = fields.get("mood", "") or ""


# Keep only what the model produced, so page identity stays current.
def _page_fields(content: PageContent) -> dict:
    return {
        "page_text": content.page_text,
        "description": content.description,
        "mood": content.mood,
    }


def understand_book(
    book: Book,
    client: VisionClient,
    *,
    cache: Cache | None = None,
) -> BookContent:
    """Read every page of a book and collect the results."""
    content = BookContent(
        id=book.id,
        title=book.title,
        source=book.source,
    )

    ns = f"understand/{book.id}"
    # A bad page only sets PageContent.error, so the loop keeps going.
    for page in book.pages:
        result = understand_page(page, client, cache=cache, ns=ns)
        content.pages.append(result)

    return content


def save_book(content: BookContent, root: str | Path | None = None) -> Path:
    """Write the book content to <root>/<book_id>/book.json."""
    base = Path(root) if root is not None else out_root()
    path = base / content.id / "book.json"

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(content.to_dict(), ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
    return path
