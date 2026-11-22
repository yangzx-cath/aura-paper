"""Pick the figure crops that later become character references."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ..media.image import crop_box, load_image, save_jpeg
from ..schema.content import BookContent, Figure, PageContent
from .paths import book_dir, figure_name, figures_dir

# A crop below this share of the page is too small to show a character.
MIN_AREA = 0.05

# A crop sharing more than this share with a neighbour cannot stand alone.
MAX_OVERLAP = 0.3

# Faces first, then profiles, then side views.
FACING_RANK = {"正面": 3, "斜侧": 2, "侧面": 1}

# Crops come from an already encoded page, so keep the second encode clean.
FIGURE_QUALITY = 95


@dataclass
class FigurePick:
    """One figure crop that may become a character reference."""

    page: str
    figure: int
    file: str
    facing: str
    area: float


def pick_figures(
    book_id: str,
    *,
    root: str | Path | None = None,
) -> list[FigurePick]:
    """Crop every usable figure to the figures folder, best first."""
    directory = book_dir(book_id, root)
    pages_dir = directory / "pages"
    out_dir = figures_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)

    picks = []
    for page in _read_content(directory).pages:
        chosen = [figure for figure in page.figures if _usable(page, figure)]
        if not chosen:
            continue
        image = load_image(pages_dir / page.filename)
        for figure in chosen:
            picks.append(_save(image, page, figure, out_dir))

    picks.sort(key=_rank, reverse=True)
    return picks


# Read the understand stage's record of the book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    text = path.read_text(encoding="utf-8")
    return BookContent.from_dict(json.loads(text))


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


# Cut one figure out of its page and keep the record of it.
def _save(
    image: Image.Image,
    page: PageContent,
    figure: Figure,
    out_dir: Path,
) -> FigurePick:
    box = figure.box
    assert box is not None
    left, top, right, bottom = box
    name = figure_name(page.filename, figure.index)
    crop = crop_box(image, (left, top, right, bottom))
    save_jpeg(crop, out_dir / name, FIGURE_QUALITY)
    return FigurePick(
        page=page.filename,
        figure=figure.index,
        file=name,
        facing=figure.facing,
        area=_area(box),
    )


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
def _rank(pick: FigurePick) -> tuple[int, float]:
    return (FACING_RANK[pick.facing], pick.area)
