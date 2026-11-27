from pathlib import Path

from aura_paper.media.pdf import render_pdf
from PIL import Image


# Pillow writes one point per pixel, so 200x300 pt scales by dpi/72.
def make_pdf(path: Path, pages: int = 2) -> Path:
    images = [Image.new("RGB", (200, 300), "white") for _ in range(pages)]
    images[0].save(path, "PDF", save_all=True, append_images=images[1:])
    return path


def test_renders_every_page_to_a_jpeg(tmp_path):
    pdf = make_pdf(tmp_path / "book.pdf")

    pages = render_pdf(pdf, tmp_path / "source", dpi=144)

    assert [page.filename for page in pages] == [
        "pdf_000.jpg",
        "pdf_001.jpg",
    ]
    assert [(page.width, page.height) for page in pages] == [(400, 600)] * 2
    assert [page.index for page in pages] == [0, 1]
    for page in pages:
        assert (tmp_path / "source" / page.filename).is_file()
