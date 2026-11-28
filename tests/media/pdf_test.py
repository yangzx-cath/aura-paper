import pytest
from PIL import Image

from aura_paper.media.pdf import PdfError, _clean_text, render_pdf


def test_render_pdf_rejects_a_file_that_is_not_a_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(PdfError):
        render_pdf(path, tmp_path / "source")


def test_render_pdf_rejects_a_dpi_below_the_document_resolution(tmp_path):
    path = tmp_path / "book.pdf"
    Image.new("RGB", (200, 300), "white").save(path, "PDF")

    with pytest.raises(ValueError):
        render_pdf(path, tmp_path / "source", dpi=71)


def test_clean_text_drops_a_layer_that_decoded_into_garbage():
    assert _clean_text("\ufffd\ufffd\ufffd") == ""


def test_clean_text_keeps_a_layer_with_a_few_bad_characters():
    assert _clean_text("abc\ufffd") == "abc\ufffd"


def test_clean_text_normalizes_line_breaks():
    assert _clean_text(" a\r\nb\rc ") == "a\nb\nc"
