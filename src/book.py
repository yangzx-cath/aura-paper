"""
Book input component: load a book source into a structured Book.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


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
    source: str  # directory or PDF path, set by load()
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
        kinds: dict[str | int, str] | None = None,
    ) -> None:
        """Load the pages of this book from a source path.

        Args:
            source: image directory or PDF file.
            default_kind: kind for every page, one of PAGE_KINDS.
            kinds: per-page overrides, keyed by image filename for a directory
                source or by 1-based page number for a PDF source,
                e.g. {"003.jpg": "spread"} or {3: "spread"}.
        """
        if self.pages:
            raise RuntimeError(
                f"{self.id!r} is already loaded from {self.source!r}"
            )

        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"source does not exist: {path}")

        assert default_kind in PAGE_KINDS
        if path.is_dir():
            pages = self._load_dir(path, default_kind, kinds)
        elif path.suffix.lower() == ".pdf":
            pages = self._load_pdf(path, default_kind, kinds)
        else:
            raise ValueError(f"unsupported source: {path}")

        # Assign only after everything succeeded, so a failure keeps old pages.
        self.pages = pages
        self.source = str(path)

    @staticmethod
    def _load_dir(
        directory: Path,
        default_kind: str,
        kinds: dict[str | int, str] | None,
    ) -> list[PageImage]:
        images: list[Path] = []
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            if entry.name.startswith("."):
                continue
            if entry.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            images.append(entry)

        if not images:
            raise ValueError(f"no supported images in {directory}")

        images.sort(key=lambda p: _natural_key(p.name))
        overrides = _kinds_for_dir(kinds, images)

        pages: list[PageImage] = []
        for index, image in enumerate(images):
            pages.append(
                PageImage(
                    index=index,
                    filename=image.name,
                    path=str(image),
                    kind=overrides.get(image.name, default_kind),
                )
            )
        return pages

    @staticmethod
    def _load_pdf(
        pdf_path: Path,
        default_kind: str,
        kinds: dict[str | int, str] | None,
    ) -> list[PageImage]:
        raise NotImplementedError("Book._load_pdf")


# Sort filenames by their numeric parts, so page_2 comes before page_10.
def _natural_key(name: str) -> tuple:
    parts = re.split(r"(\d+)", name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


# Validate a kinds map for a directory source, keyed by filename.
def _kinds_for_dir(
    kinds: dict[str | int, str] | None,
    images: list[Path],
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for key, kind in (kinds or {}).items():
        if not isinstance(key, str):
            raise ValueError(
                f"kinds key must be a filename for a directory source: {key!r}"
            )
        if kind not in PAGE_KINDS:
            raise ValueError(f"invalid kind for {key!r}: {kind!r}")
        overrides[key] = kind

    unknown = set(overrides) - {p.name for p in images}
    if unknown:
        raise ValueError(f"unknown page filenames: {sorted(unknown)}")

    return overrides
