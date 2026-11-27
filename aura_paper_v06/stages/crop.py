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
from ..schema.content import BookContent, Figure, PageContent
from ..schema.crop import BookCrop, FigureCrop, PageCrop, PanelCrop
from ..store.output import write_json
from .paths import (
    book_dir,
    figure_name,
    figures_dir,
    panel_name,
    panels_dir,
)

# Panels are cut from an already encoded page, so keep the second encode clean.
PANEL_QUALITY = 95

# Figure crops are read as character look, so keep them clean too.
FIGURE_QUALITY = 95

# A figure crop below this share of the page is too small to show a character.
MIN_AREA = 0.05

# A crop sharing more than this share with a neighbour cannot stand alone.
MAX_OVERLAP = 0.3

# Faces first, then profiles, then side views.
FACING_RANK = {"正面": 3, "斜侧": 2, "侧面": 1}

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
    figures_out = figures_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.rmtree(figures_out, ignore_errors=True)

    result = BookCrop(id=book_id, language=content.language)
    pages_dir = directory / "pages"
    cover = content.cover_page
    for page in content.pages:
        if not page.panels and not page.figures:
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
        result.figures.extend(_cut_figures(page, image, figures_out))
        result.pages.append(
            PageCrop(
                filename=page.filename,
                erased=erase,
                lines=len(text),
            )
        )
    result.figures.sort(key=_rank, reverse=True)
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


# Cut every usable figure of one page out of its image.
def _cut_figures(
    page: PageContent,
    image: Image.Image,
    out_dir: Path,
) -> list[FigureCrop]:
    crops = []
    for figure in page.figures:
        if not _usable(page, figure):
            continue
        box = figure.box
        assert box is not None
        left, top, right, bottom = box
        name = figure_name(page.filename, figure.index)
        cut = crop_box(image, (left, top, right, bottom))
        save_jpeg(cut, out_dir / name, FIGURE_QUALITY)
        crops.append(
            FigureCrop(
                page=page.filename,
                figure=figure.index,
                file=name,
                facing=figure.facing,
                area=_area(box),
            )
        )
    return crops


# Tell whether a figure can stand alone as a reference image.
def _usable(page: PageContent, figure: Figure) -> bool:
    box = figure.box
    if box is None:
        return False
    if figure.view != "全身" or figure.occlusion != "无":
        return False
    if figure.facing not in FACING_RANK:
        return False
    if _area(box) < MIN_AREA:
        return False
    return _worst_overlap(page, figure, box) <= MAX_OVERLAP


# Return the share of the page a per-mille box covers.
def _area(box: list[int]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1]) / 1_000_000


# Return the share of the smaller box that two boxes have in common.
def _overlap(first: list[int], second: list[int]) -> float:
    width = min(first[2], second[2]) - max(first[0], second[0])
    height = min(first[3], second[3]) - max(first[1], second[1])
    if width <= 0 or height <= 0:
        return 0.0
    shared = width * height / 1_000_000
    return shared / min(_area(first), _area(second))


# Return the largest share this figure box shares with another on the page.
def _worst_overlap(
    page: PageContent,
    figure: Figure,
    box: list[int],
) -> float:
    overlaps = []
    for other in page.figures:
        if other is figure or other.box is None:
            continue
        overlaps.append(_overlap(box, other.box))
    return max(overlaps, default=0.0)


# Sort key: faces before profiles, then the larger crop.
def _rank(crop: FigureCrop) -> tuple[int, float]:
    return (FACING_RANK[crop.facing], crop.area)
