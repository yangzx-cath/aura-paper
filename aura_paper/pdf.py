"""
Render page images and read any text layer from a PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .output import write_json
from .utils import now_iso

# 200 dpi keeps printed text sharp for the vision model.
DEFAULT_DPI = 200
MIN_DPI = 72
MAX_DPI = 600

IMAGE_FORMAT = "jpg"
IMAGE_QUALITY = 92

PAGE_TEMPLATE = "page_{number:03d}.jpg"


class PdfError(Exception):
    """Error for PDF input."""


@dataclass
class PdfPage:
    """One page of a PDF, rendered to an image file."""

    index: int
    filename: str
    width: int = 0
    height: int = 0
    text: str = ""  # Empty when the PDF has no usable text layer.

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
    def from_dict(cls, data: dict) -> PdfPage:
        """Build a page from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            filename=str(data.get("filename") or ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            text=str(data.get("text") or ""),
        )


@dataclass
class PdfContent:
    """Every page of one PDF, rendered to image files."""

    id: str
    source: str
    directory: str = ""
    dpi: int = DEFAULT_DPI
    pages: list[PdfPage] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    # Pages whose printed text the PDF itself carries, for cross-checking.
    @property
    def text_pages(self) -> int:
        return sum(1 for page in self.pages if page.text)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this content."""
        return {
            "id": self.id,
            "source": self.source,
            "directory": self.directory,
            "generated_at": now_iso(),
            "dpi": self.dpi,
            "page_count": self.page_count,
            "text_pages": self.text_pages,
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PdfContent:
        """Build content from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            source=str(data.get("source") or ""),
            directory=str(data.get("directory") or ""),
            dpi=int(data.get("dpi") or DEFAULT_DPI),
            pages=[
                PdfPage.from_dict(page) for page in data.get("pages") or []
            ],
        )


def render_pdf(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    quality: int = IMAGE_QUALITY,
    on_page: Callable[[PdfPage, float], None] | None = None,
) -> PdfContent:
    """Render every page of a PDF into out_dir, returning its pages.

    Page text comes from the PDF text layer and stays empty when that
    layer is missing or unusable.
    """
    raise NotImplementedError("render_pdf() is not implemented yet")


def save_pages(
    content: PdfContent,
    root: str | Path | None = None,
) -> Path:
    """Write the rendered pages to <root>/<id>/pages.json."""
    return write_json(content.id, "pages", content.to_dict(), root)
