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
    default_kind: str = "single",
    kinds: dict[str, str] | None = None,
) -> Book:
    """Load a book from an image directory."""
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"source does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"not an image directory: {path}")

    assert default_kind in PAGE_KINDS

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
    overrides = _validate_kinds(kinds, images)

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
                kind=overrides.get(image.name, default_kind),
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


# Validate per-page kinds and return them keyed by filename.
def _validate_kinds(
    kinds: dict[str, str] | None,
    images: list[Path],
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for key, kind in (kinds or {}).items():
        if not isinstance(key, str):
            raise ValueError(f"kinds key must be a filename: {key!r}")
        if kind not in PAGE_KINDS:
            raise ValueError(f"invalid kind for {key!r}: {kind!r}")
        overrides[key] = kind

    unknown = set(overrides) - {p.name for p in images}
    if unknown:
        raise ValueError(f"unknown page filenames: {sorted(unknown)}")

    return overrides


# Read an image header and return its (width, height).
def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size
