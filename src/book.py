"""
Book input component: load an image directory into a structured Book.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# Page kinds
PAGE_KINDS = ("single", "spread")

# Image suffixes accepted
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


@dataclass
class PageImage:
    """One page of a book, backed by a single image file."""

    index: int
    filename: str
    path: str
    width: int | None = None
    height: int | None = None
    kind: str = "single"  # one of PAGE_KINDS, set manually


class Book:
    """A book: an ordered list of pages."""

    id: str
    title: str
    source: str  # image directory, set by load()
    pages: list[PageImage]

    def __init__(self, id: str, title: str = "") -> None:
        self.id = id
        self.title = title
        self.source = ""
        self.pages = []

    def __repr__(self) -> str:
        count = self.page_count
        return f"Book(id={self.id!r}, title={self.title!r}, pages={count})"

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def load(
        self,
        source: str | Path,
        *,
        default_kind: str = "single",
        kinds: dict[str, str] | None = None,
    ) -> None:
        """Load the pages of this book from an image directory.

        Args:
            source: directory holding the page images.
            default_kind: kind for every page, one of PAGE_KINDS.
            kinds: per-page overrides keyed by filename,
                e.g. {"003.jpg": "spread"}.
        """
        if self.pages:
            raise RuntimeError(
                f"{self.id!r} is already loaded from {self.source!r}"
            )

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
            if entry.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            images.append(entry)

        if not images:
            raise ValueError(f"no supported images in {path}")

        images.sort(key=lambda p: _natural_key(p.name))
        overrides = _validate_kinds(kinds, images)

        pages: list[PageImage] = []
        for index, image in enumerate(images):
            size = _image_size(image)
            width, height = size if size else (None, None)
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

        # Assign only after everything succeeded, so a failure keeps old pages.
        self.pages = pages
        self.source = str(path)


# Sort filenames by their numeric parts, so page_2 comes before page_10.
def _natural_key(name: str) -> tuple:
    parts = re.split(r"(\d+)", name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


# Validate a kinds map, keyed by filename.
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


# Read an image header and return its (width, height), or None on failure.
def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        # A broken file must not break loading the whole book.
        return None
