"""Load page images from a directory into a book."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .utils import IMAGE_SUFFIXES

# Page kinds
PAGE_KINDS = ("single", "spread")


@dataclass
class PageImage:
    """One page image of a book."""

    index: int
    filename: str
    path: str
    width: int | None = None
    height: int | None = None
    kind: str = "single"  # one of PAGE_KINDS


@dataclass
class Book:
    """One book and its ordered page images."""

    id: str
    title: str = ""
    source: str = ""
    pages: list[PageImage] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def load_book(
    source: str | Path,
    *,
    book_id: str = "",
    title: str = "",
) -> Book:
    """Load a book from an image directory."""
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

    pages: list[PageImage] = []
    for index, image in enumerate(images):
        width, height = _image_size(image)
        pages.append(
            PageImage(
                index=index,
                filename=image.name,
                path=str(image),
                width=width,
                height=height,
                kind=_kind(width, height),
            )
        )

    return Book(
        id=str(book_id or "").strip() or path.name,
        title=title,
        source=str(path),
        pages=pages,
    )


# Build a sort key so page_2 comes before page_10.
def _natural_key(name: str) -> tuple:
    parts = re.split(r"(\d+)", name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


# A wide scan usually holds two pages side by side.
def _kind(width: int, height: int) -> str:
    return "spread" if width > height else "single"


# Read an image header and return its (width, height).
def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size
