"""
Interpret page images into structured content.
"""

from dataclasses import dataclass, field
from pathlib import Path

from aura_paper.book import Book, PageImage
from aura_paper.prompts import page_prompt
from aura_paper.vision import VisionClient, VisionError, extract_json


@dataclass
class PageContent:
    """Structured content of one page."""

    index: int
    filename: str
    page_text: str = ""
    description: str = ""
    mood: str = ""
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        raise NotImplementedError("PageContent.to_dict")


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
        raise NotImplementedError("BookContent.to_dict")


def understand_page(page: PageImage, client: VisionClient) -> PageContent:
    """Read one page and return its structured content."""
    content = PageContent(
        index=page.index,
        filename=page.filename,
        model=client.model,
    )

    prompt = page_prompt(page.kind)
    image_path = Path(page.path)

    try:
        reply = client.analyze(prompt, image_path)
        fields = extract_json(reply)
    except (VisionError, ValueError) as exc:
        content.error = str(exc)
        return content

    # Missing or null fields become empty strings.
    content.page_text = fields.get("page_text", "") or ""
    content.description = fields.get("description", "") or ""
    content.mood = fields.get("mood", "") or ""

    if not content.page_text and not content.description:
        content.error = "model returned no content"

    return content


def understand_book(book: Book, client: VisionClient) -> BookContent:
    """Read every page of a book and collect the results."""
    content = BookContent(
        id=book.id,
        title=book.title,
        source=book.source,
    )

    # A bad page only sets PageContent.error, so the loop keeps going.
    for page in book.pages:
        content.pages.append(understand_page(page, client))

    return content
