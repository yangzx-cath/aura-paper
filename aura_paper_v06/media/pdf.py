"""Render PDF pages to JPEG images and read their text layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

# 200 dpi keeps printed text sharp for the vision model.
DEFAULT_DPI = 200
DEFAULT_QUALITY = 92

# Numbered from zero: the first page of a picture book is its cover.
PAGE_TEMPLATE = "pdf_{index:03d}.jpg"


class PdfError(Exception):
    """Error for PDF input."""


@dataclass
class RenderedPage:
    """One PDF page written to disk."""

    index: int
    filename: str
    width: int
    height: int
    text: str = ""


def render_pdf(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    quality: int = DEFAULT_QUALITY,
) -> list[RenderedPage]:
    """Render every page into out_dir and return one record per page."""
    source = Path(pdf_path).expanduser()
    target = Path(out_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)

    try:
        doc = pdfium.PdfDocument(str(source))
    except pdfium.PdfiumError as exc:
        raise PdfError(f"{source.name}: {exc}") from exc

    pages: list[RenderedPage] = []
    try:
        for index in range(len(doc)):
            pages.append(_render_page(doc, index, target, dpi, quality))
    finally:
        doc.close()
    return pages


# Render one page, read its text and write the jpg.
def _render_page(
    doc: pdfium.PdfDocument,
    index: int,
    out_dir: Path,
    dpi: int,
    quality: int,
) -> RenderedPage:
    name = PAGE_TEMPLATE.format(index=index)
    page = doc[index]
    try:
        # PDF user units are points, 72 to an inch, so the scale turns
        # dpi into that unit. pypdfium2 leaves scale unannotated, so
        # Pyright reads it as int even though a float is valid.
        scale = dpi / 72
        image = page.render(scale=scale).to_pil().copy()  # pyright: ignore
        text = _page_text(page)
    finally:
        page.close()

    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(out_dir / name, "JPEG", quality=quality, optimize=True)

    width, height = image.size
    return RenderedPage(
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


# Normalize line breaks and drop a layer that decoded into garbage.
def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # A wrong encoding decodes into replacement characters.
    if text.count("\ufffd") * 3 > len(text):
        return ""
    return text
