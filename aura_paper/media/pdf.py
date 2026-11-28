"""Render a PDF into source page images and read the text layer."""

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

# 200 dpi keeps printed text sharp.
DEFAULT_DPI = 200
DEFAULT_QUALITY = 92

# Source pages are numbered from one, the way the PDF counts them.
SOURCE_TEMPLATE = "source{index:03d}.jpg"


class PdfError(Exception):
    """Raised when a PDF cannot be loaded or rendered."""


@dataclass
class SourcePage:
    """One page of the PDF, rendered to an image file."""

    index: int
    filename: str
    width: int
    height: int
    text: str = ""


def render_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    quality: int = DEFAULT_QUALITY,
) -> list[SourcePage]:
    """Render every page into output_dir and return one record per page."""
    source = Path(pdf_path).expanduser()
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        document = pdfium.PdfDocument(str(source))
    except pdfium.PdfiumError as exc:
        raise PdfError(f"{source.name}: {exc}") from exc

    pages: list[SourcePage] = []
    try:
        for index in range(len(document)):
            page = _render_page(document, index, output_dir, dpi, quality)
            pages.append(page)
    finally:
        document.close()
    return pages


# Render one page to a JPEG and read the text written on it.
def _render_page(
    document: pdfium.PdfDocument,
    index: int,
    output_dir: Path,
    dpi: int,
    quality: int,
) -> SourcePage:
    number = index + 1
    name = SOURCE_TEMPLATE.format(index=number)
    page = document[index]
    try:
        # PDF user units are points, 72 to an inch, so this scale turns
        # dpi into that unit. pypdfium2 leaves scale unannotated, so the
        # type checker reads it as int even though a float is valid.
        scale = dpi / 72
        bitmap = page.render(scale=scale)  # pyright: ignore
        image = bitmap.to_pil().copy()
        text = _page_text(page)
    finally:
        page.close()

    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(output_dir / name, "JPEG", quality=quality, optimize=True)

    width, height = image.size
    return SourcePage(
        index=number,
        filename=name,
        width=width,
        height=height,
        text=text,
    )


# Read the text layer of one page.
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
