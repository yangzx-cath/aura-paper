"""The source pages of one book, before they are understood."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .utils import IMAGE_SUFFIXES


@dataclass
class Page:
    """One page image of a book, as the source provides it."""

    index: int
    filename: str
    width: int = 0
    height: int = 0
    text: str = ""  # Printed text read from the PDF text layer.


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


def load_images(
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
