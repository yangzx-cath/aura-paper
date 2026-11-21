"""Crop the chosen reference image for each character."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import out_root
from .story import Story
from .understand import BookContent, Figure

# Room left around the crop box, so a tight box cannot clip a limb.
MARGIN = 0.04
# A video model rejects a reference whose short side is below this.
MIN_SIDE = 300
# It also rejects one whose width/height falls outside this range.
MIN_RATIO = 0.4
MAX_RATIO = 2.5
# Enlarging a small crop further than this only adds blur.
MAX_ZOOM = 1.6
# High enough for line art, small enough to keep the upload light.
QUALITY = 92


@dataclass
class ReferenceImage:
    """One character's reference image, cut out of its page."""

    name: str
    page: int
    figure: int
    path: Path
    width: int = 0
    height: int = 0


def reference_path(
    book_id: str,
    name: str,
    root: str | Path | None = None,
) -> Path:
    """Return <root>/<book_id>/references/<name>.jpg."""
    return _reference_dir(book_id, root) / f"{name}.jpg"


# Return the folder that holds one book's reference images.
def _reference_dir(book_id: str, root: str | Path | None) -> Path:
    base = Path(root) if root is not None else out_root()
    return base / book_id / "references"


def save_references(
    content: BookContent,
    story: Story,
    directory: str | Path,
    root: str | Path | None = None,
) -> list[ReferenceImage]:
    """Crop each character's reference image out of its page."""
    pages = {page.index: page for page in content.pages}
    folder = _reference_dir(story.id, root)
    folder.mkdir(parents=True, exist_ok=True)
    _clear_files(folder)

    written = []
    for reference in story.references:
        page = pages.get(reference.page)
        if page is None or not 0 <= reference.figure < len(page.figures):
            continue
        figure = page.figures[reference.figure]
        image = _crop(Path(directory) / page.filename, figure)
        if image is None:
            continue
        path = folder / f"{reference.name}.jpg"
        image.save(path, format="JPEG", quality=QUALITY)
        written.append(
            ReferenceImage(
                name=reference.name,
                page=reference.page,
                figure=reference.figure,
                path=path,
                width=image.width,
                height=image.height,
            )
        )
    return written


# Drop old crops, including any left by a former format.
def _clear_files(folder: Path) -> None:
    for entry in folder.iterdir():
        if entry.is_file():
            entry.unlink()


# Cut one figure out of its page, or return None when that is impossible.
def _crop(
    page_path: Path,
    figure: Figure,
) -> Image.Image | None:
    box = _box(figure.box)
    if box is None:
        return None
    try:
        with Image.open(page_path) as image:
            page = image.convert("RGB")
    except OSError:
        return None

    piece = page.crop(_padded(box, page.size))
    if piece.width <= 0 or piece.height <= 0:
        return None
    if not MIN_RATIO <= piece.width / piece.height <= MAX_RATIO:
        return None
    if min(piece.size) < MIN_SIDE:
        zoom = min(MIN_SIDE / min(piece.size), MAX_ZOOM)
        size = (round(piece.width * zoom), round(piece.height * zoom))
        piece = piece.resize(size, Image.Resampling.LANCZOS)
        if min(piece.size) < MIN_SIDE:
            # The capped zoom is still too small to be accepted.
            return None
    return piece


# Read a box as four ordered integers, or None when it is unusable.
# Box values are percentages of the page, normally between 0 and 100.
def _box(box: list[int] | None) -> tuple[int, int, int, int] | None:
    if not box or len(box) != 4:
        return None
    try:
        left, top, right, bottom = (int(value) for value in box)
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


# Grow the percentage box by MARGIN and keep it inside the page.
def _padded(
    box: tuple[int, int, int, int],
    size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = size
    left, top, right, bottom = box
    dx = (right - left) * MARGIN
    dy = (bottom - top) * MARGIN
    return (
        min(width, max(0, round((left - dx) / 100 * width))),
        min(height, max(0, round((top - dy) / 100 * height))),
        min(width, max(0, round((right + dx) / 100 * width))),
        min(height, max(0, round((bottom + dy) / 100 * height))),
    )
