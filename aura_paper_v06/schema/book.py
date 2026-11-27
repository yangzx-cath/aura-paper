"""Logical pages produced by the ingest stage."""

from __future__ import annotations

from dataclasses import dataclass, field

from .time import now_iso


@dataclass
class Page:
    """One logical page, made from one or two PDF pages."""

    index: int
    filename: str
    width: int
    height: int
    sources: list[int] = field(default_factory=list)
    boxes: list[list[int]] = field(default_factory=list)
    origin: str = "page"  # "page", "spread" or "half"
    text: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        return {
            "index": self.index,
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "sources": self.sources,
            "boxes": self.boxes,
            "origin": self.origin,
            "text": self.text,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Page:
        """Build a page from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            filename=str(data.get("filename") or ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            sources=_int_list(data.get("sources")),
            boxes=_box_list(data.get("boxes")),
            origin=str(data.get("origin") or "page"),
            text=str(data.get("text") or ""),
            error=str(data.get("error") or ""),
        )


# Read a list of source page numbers.
def _int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    numbers = []
    for item in value:
        if isinstance(item, int):
            numbers.append(item)
    return numbers


# Read percent boxes, keeping only four-number entries.
def _box_list(value: object) -> list[list[int]]:
    if not isinstance(value, list):
        return []
    boxes = []
    for item in value:
        if not isinstance(item, list) or len(item) != 4:
            continue
        try:
            boxes.append([int(number) for number in item])
        except (TypeError, ValueError):
            continue
    return boxes


@dataclass
class Book:
    """One book after ingest."""

    id: str
    source: str = ""
    dpi: int = 0
    pair_from: int = 1
    source_count: int = 0
    pages: list[Page] = field(default_factory=list)
    error: str = ""

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book."""
        pages = []
        for page in self.pages:
            pages.append(page.to_dict())
        return {
            "id": self.id,
            "source": self.source,
            "generated_at": now_iso(),
            "dpi": self.dpi,
            "pair_from": self.pair_from,
            "source_count": self.source_count,
            "page_count": self.page_count,
            "pages": pages,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Book:
        """Build a book from its external JSON shape."""
        pages = []
        for item in data.get("pages") or []:
            if isinstance(item, dict):
                pages.append(Page.from_dict(item))
        return cls(
            id=str(data.get("id") or ""),
            source=str(data.get("source") or ""),
            dpi=int(data.get("dpi") or 0),
            pair_from=int(data.get("pair_from") or 1),
            source_count=int(data.get("source_count") or 0),
            pages=pages,
            error=str(data.get("error") or ""),
        )
