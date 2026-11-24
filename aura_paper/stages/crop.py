"""Cut one image per panel out of the page images.

An English book has its printed text filled out of each page once, before
any panel is cut. The cover is left as printed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from ..media.erase import Poly, crop_without_text, page_array, text_boxes
from ..media.image import crop_box, load_image, save_jpeg
from ..schema.content import BookContent, PageContent
from ..schema.crop import BookCrop, PageCrop, PanelCrop
from ..store.output import write_json
from .paths import book_dir, panel_name, panels_dir

# Panels are cut from an already encoded page, so keep the second encode clean.
PANEL_QUALITY = 95

# The mask around a printed line grows by this many pixels.
MARGIN = 3

# A line whose surroundings differ by less than this takes their colour.
FLAT_LIMIT = 25

# A box that covers the whole page.
WHOLE = [0, 0, 1000, 1000]


def crop(
    book_id: str,
    *,
    root: str | Path | None = None,
) -> BookCrop:
    """Cut every panel box to its own file and write crop.json."""
    directory = book_dir(book_id, root)
    content = _read_content(directory)
    out_dir = panels_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)

    result = BookCrop(id=book_id, language=content.language)
    pages_dir = directory / "pages"
    cover = content.cover_page
    for page in content.pages:
        if not page.panels:
            continue
        source = pages_dir / page.filename
        image = load_image(source)
        erase = content.language == "en" and page is not cover
        text: list[Poly] = []
        if erase:
            text = text_boxes(source)
            image = crop_without_text(
                page_array(image),
                WHOLE,
                text,
                margin=MARGIN,
                flat_limit=FLAT_LIMIT,
            )
        result.panels.extend(_cut_page(page, image, out_dir))
        result.pages.append(
            PageCrop(
                filename=page.filename,
                erased=erase,
                lines=len(text),
            )
        )
    if not result.panels:
        result.error = "understand.json holds no panel box"
    write_json(book_id, "crop", result.to_dict(), root)
    return result


# Read the understand stage's record of the book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    text = path.read_text(encoding="utf-8")
    return BookContent.from_dict(json.loads(text))


# Cut every panel of one page out of its image.
def _cut_page(
    page: PageContent,
    image: Image.Image,
    out_dir: Path,
) -> list[PanelCrop]:
    crops = []
    for panel in page.panels:
        box = panel.box
        assert box is not None
        left, top, right, bottom = box
        cut = crop_box(image, (left, top, right, bottom))
        name = panel_name(page.filename, panel.index)
        save_jpeg(cut, out_dir / name, PANEL_QUALITY)
        crops.append(
            PanelCrop(
                page=page.filename,
                index=panel.index,
                file=name,
                box=list(box),
            )
        )
    return crops
