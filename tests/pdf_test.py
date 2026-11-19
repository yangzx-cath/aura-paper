from pathlib import Path

import pytest
from PIL import Image

from aura_paper.pdf import (
    MAX_DPI,
    MIN_DPI,
    PdfError,
    _clean_text,
    render_pdf,
)


# Write a one page PDF, 200x300 pt because Pillow writes points one to one.
def make_pdf(path: Path, size=(200, 300)) -> Path:
    Image.new("RGB", size, "white").save(path, "PDF")
    return path


def test_scales_the_page_to_the_dpi(tmp_path):
    pdf = make_pdf(tmp_path / "book.pdf")

    content = render_pdf(pdf, tmp_path / "pages", dpi=144)

    # Pillow writes points one to one, so 200x300pt at 2x is 400x600 px.
    page = content.pages[0]
    assert (page.width, page.height) == (400, 600)


def test_clamps_dpi_to_the_supported_range(tmp_path):
    pdf = make_pdf(tmp_path / "book.pdf")

    low = render_pdf(pdf, tmp_path / "low", dpi=10)
    high = render_pdf(pdf, tmp_path / "high", dpi=2000)

    assert low.dpi == MIN_DPI
    assert high.dpi == MAX_DPI


def test_rejects_a_quality_outside_the_jpeg_range(tmp_path):
    pdf = make_pdf(tmp_path / "book.pdf")

    with pytest.raises(ValueError, match="quality must be"):
        render_pdf(pdf, tmp_path / "pages", quality=200)


def test_rejects_a_file_that_is_not_a_pdf(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(PdfError, match="bad.pdf"):
        render_pdf(path, tmp_path / "pages")


def test_raises_when_the_file_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_pdf(tmp_path / "missing.pdf", tmp_path / "pages")


def test_clean_text_normalizes_line_breaks():
    assert _clean_text("  a\r\nb\rc  ") == "a\nb\nc"


def test_clean_text_drops_a_broken_layer():
    assert _clean_text("\ufffd\ufffd\ufffd\ufffd") == ""
    assert _clean_text("\ufffd\ufffd\ufffd a") == ""


def test_clean_text_keeps_a_stray_replacement_char():
    assert _clean_text("usable \ufffd") == "usable \ufffd"
