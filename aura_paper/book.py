"""The source pages of one book, before they are understood."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .utils import IMAGE_SUFFIXES, now_iso


@dataclass
class Page:
    """One page image of a book, as the source provides it."""

    index: int
    filename: str
    width: int = 0
    height: int = 0
    text: str = ""  # Printed text read from the PDF text layer.

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        return {
            "index": self.index,
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Page:
        """Build a page from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            filename=str(data.get("filename") or ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            text=str(data.get("text") or ""),
        )


@dataclass
class Book:
    """One book and its ordered pages."""

    id: str
    source: str = ""  # Where the pages came from.
    directory: str = ""  # Where the page images live.
    dpi: int = 0
    title: str = ""
    pages: list[Page] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    # Pages whose source carried printed text, for cross-checking.
    @property
    def text_pages(self) -> int:
        return sum(1 for page in self.pages if page.text)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book."""
        return {
            "id": self.id,
            "source": self.source,
            "directory": self.directory,
            "generated_at": now_iso(),
            "dpi": self.dpi,
            "title": self.title,
            "page_count": self.page_count,
            "text_pages": self.text_pages,
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Book:
        """Build a book from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            source=str(data.get("source") or ""),
            directory=str(data.get("directory") or ""),
            dpi=int(data.get("dpi") or 0),
            title=str(data.get("title") or ""),
            pages=[Page.from_dict(page) for page in data.get("pages") or []],
        )


def load_book_from_images(
    source: str | Path,
    *,
    book_id: str = "",
    title: str = "",
) -> Book:
    """Build a book from a directory of page images."""
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"source does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"not an image directory: {path}")

    images: list[Path] = []
    for entry in path.iterdir():
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        if entry.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        images.append(entry)

    if not images:
        raise ValueError(f"no supported images in {path}")

    images.sort(key=lambda p: _natural_key(p.name))

    pages: list[Page] = []
    for index, image in enumerate(images):
        width, height = _image_size(image)
        pages.append(
            Page(
                index=index,
                filename=image.name,
                width=width,
                height=height,
            )
        )

    return Book(
        id=str(book_id or "").strip() or path.name,
        source=str(path),
        directory=str(path),
        title=title,
        pages=pages,
    )


# Build a sort key so page_2 comes before page_10.
def _natural_key(name: str) -> tuple:
    parts = re.split(r"(\d+)", name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


# Read an image header and return its (width, height).
def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size
