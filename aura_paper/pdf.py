"""
Render page images and read any text layer from a PDF.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium

from .book import Book, Page

# 200 dpi keeps printed text sharp for the vision model.
DEFAULT_DPI = 200
MIN_DPI = 72
MAX_DPI = 600

IMAGE_QUALITY = 92
MIN_QUALITY = 1
MAX_QUALITY = 100

# Numbered from zero: the first page of a picture book is its cover.
PAGE_TEMPLATE = "page_{number:03d}.jpg"


class PdfError(Exception):
    """Error for PDF input."""


def render_pdf(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    quality: int = IMAGE_QUALITY,
    on_page: Callable[[Page, float], None] | None = None,
) -> Book:
    """Render every page of a PDF into out_dir, returning the book."""
    if not MIN_QUALITY <= quality <= MAX_QUALITY:
        raise ValueError(
            f"quality must be {MIN_QUALITY}-{MAX_QUALITY}: {quality}"
        )

    source = Path(pdf_path).expanduser().resolve()
    target = Path(out_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    book = Book(
        id=source.stem,
        source=str(source),
        directory=str(target),
        dpi=min(MAX_DPI, max(MIN_DPI, dpi)),
    )

    try:
        doc = pdfium.PdfDocument(str(source))
    except pdfium.PdfiumError as exc:
        raise PdfError(f"{source.name}: {exc}") from exc

    for index in range(len(doc)):
        started = time.perf_counter()
        page = _render_page(doc, index, target, book.dpi, quality)
        book.pages.append(page)
        if on_page is not None:
            on_page(page, time.perf_counter() - started)

    doc.close()
    return book


# Render one page to a jpg file and read the text it carries.
def _render_page(
    doc: pdfium.PdfDocument,
    index: int,
    out_dir: Path,
    dpi: int,
    quality: int,
) -> Page:
    name = PAGE_TEMPLATE.format(number=index)
    page = doc[index]
    try:
        # PDF user units are points, 72 to an inch, so the scale turns dpi
        # into that unit.
        scale = dpi / 72
        image = page.render(scale=scale).to_pil().copy()  # pyright: ignore
        text = _page_text(page)
    finally:
        page.close()

    if image.mode != "RGB":
        image = image.convert("RGB")
    _save_jpg(image, out_dir / name, quality)
    width, height = image.size

    return Page(
        index=index,
        filename=name,
        width=width,
        height=height,
        text=text,
    )


def _page_text(page: pdfium.PdfPage) -> str:
    textpage = page.get_textpage()
    try:
        text = textpage.get_text_bounded()
    finally:
        textpage.close()
    return _clean_text(text)


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # A wrong encoding decodes into replacement characters.
    if text.count("\ufffd") * 3 > len(text):
        return ""
    return text


def _save_jpg(image, path: Path, quality: int) -> None:
    fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            image.save(
                f,
                "JPEG",
                quality=quality,
                optimize=True,
                subsampling=0,
            )
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
