"""Cut one image per panel out of the page images."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from ..media.image import crop_box, load_image, save_jpeg
from ..schema.content import BookContent, PageContent, Panel
from ..schema.crop import BookCrop, PanelCrop
from ..store.output import write_json
from .paths import book_dir, panel_name, panels_dir

# Panels are cut from an already encoded page, so keep the second encode clean.
PANEL_QUALITY = 95


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

    result = BookCrop(id=book_id)
    pages_dir = directory / "pages"
    for page in content.pages:
        if not page.panels:
            continue
        image = load_image(pages_dir / page.filename)
        for panel in page.panels:
            result.panels.append(_cut(image, page, panel, out_dir))
    if not result.panels:
        result.error = "understand.json holds no panel box"
    write_json(book_id, "crop", result.to_dict(), root)
    return result


# Read the understand stage's record of the book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    text = path.read_text(encoding="utf-8")
    return BookContent.from_dict(json.loads(text))


# Cut one panel out of its page image and save it.
def _cut(
    image: Image.Image,
    page: PageContent,
    panel: Panel,
    out_dir: Path,
) -> PanelCrop:
    box = panel.box
    assert box is not None
    left, top, right, bottom = box
    name = panel_name(page.filename, panel.index)
    crop = crop_box(image, (left, top, right, bottom))
    save_jpeg(crop, out_dir / name, PANEL_QUALITY)
    return PanelCrop(
        page=page.filename,
        index=panel.index,
        file=name,
        box=list(box),
    )
