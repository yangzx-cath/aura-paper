"""Page image operations."""

from __future__ import annotations

import base64
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat

# Supported image suffixes and their MIME types.
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# Image suffixes accepted across the pipeline.
IMAGE_SUFFIXES = set(MIME_TYPES)

# Compare seam strips in steps of this many pixels.
SEAM_STEP = 2

# A real overlap matches far better than this mean colour difference.
SEAM_LIMIT = 12.0

# Pixels darker than this count as ink.
INK_LEVEL = 235


def data_url(path: Path) -> str:
    """Convert a local image file to a data URL."""
    mime = MIME_TYPES.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported image type: {path.suffix}")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def extend_sides(
    image: Image.Image,
    size: tuple[int, int],
    *,
    soften: int = 0,
) -> Image.Image:
    """Fit one image inside size, then mirror it outward to fill the sides.

    The image keeps its whole height and sits in the middle. Each side is
    filled with the image and its mirror laid side by side, so a page with
    a white or lightly patterned border continues past its own edge. A
    soften radius blurs the filling only, leaving the page itself sharp.
    """
    width, height = size
    fitted = _contain(image.convert("RGB"), size)
    canvas = Image.new("RGB", size, "white")
    left = (width - fitted.width) // 2
    top = (height - fitted.height) // 2

    pair = Image.new("RGB", (fitted.width * 2, fitted.height))
    pair.paste(fitted, (0, 0))
    pair.paste(
        fitted.transpose(Image.Transpose.FLIP_LEFT_RIGHT),
        (fitted.width, 0),
    )

    at = left - pair.width
    while at < width:
        canvas.paste(pair, (at, top))
        at += pair.width
    if soften:
        canvas = canvas.filter(ImageFilter.GaussianBlur(soften))
    canvas.paste(fitted, (left, top))
    return canvas


def load_image(path: str | Path) -> Image.Image:
    """Read one image as RGB."""
    with Image.open(path) as image:
        return image.convert("RGB")


def save_jpeg(
    image: Image.Image,
    path: str | Path,
    quality: int,
) -> tuple[int, int]:
    """Write an RGB JPEG and return its (width, height)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(target, "JPEG", quality=quality, optimize=True)
    return image.size


def stitch_side_by_side(
    left: str | Path,
    right: str | Path,
    max_overlap: int = 0,
) -> Image.Image:
    """Place two page images side by side and return the result.

    The shorter image is scaled to the taller one's height. Up to
    max_overlap pixels shared at the fold are dropped. Nothing else is
    aligned or cropped.
    """
    left_image = load_image(left)
    right_image = load_image(right)
    if max_overlap > 0:
        overlap = _seam_overlap(left_image, right_image, max_overlap)
        if overlap > 0:
            right_image = right_image.crop(
                (overlap, 0, right_image.width, right_image.height)
            )
    height = max(left_image.height, right_image.height)
    left_image = _fit_height(left_image, height)
    right_image = _fit_height(right_image, height)

    canvas = Image.new("RGB", (left_image.width + right_image.width, height))
    canvas.paste(left_image, (0, 0))
    canvas.paste(right_image, (left_image.width, 0))
    return canvas


# Find how many pixels the inner edges of two pages share.
def _seam_overlap(
    left_image: Image.Image,
    right_image: Image.Image,
    max_width: int,
) -> int:
    width = left_image.width
    height = min(left_image.height, right_image.height)

    best_width = 0
    best_score = None
    for overlap in range(SEAM_STEP, max_width + 1, SEAM_STEP):
        left_strip = left_image.crop((width - overlap, 0, width, height))
        right_strip = right_image.crop((0, 0, overlap, height))
        diff = ImageChops.difference(left_strip, right_strip)
        score = sum(ImageStat.Stat(diff).mean) / 3
        if best_score is None or score < best_score:
            best_score = score
            best_width = overlap

    if best_score is None or best_score > SEAM_LIMIT:
        return 0
    # A blank edge matches at every width, so the first step means nothing.
    if best_width <= SEAM_STEP:
        return 0
    return best_width


# Scale an image so it fits inside a box, keeping its shape.
def _contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    scale = min(width / image.width, height / image.height)
    return image.resize(
        (
            max(1, round(image.width * scale)),
            max(1, round(image.height * scale)),
        ),
        Image.Resampling.LANCZOS,
    )


# Scale an image to the given height, keeping its shape.
def _fit_height(image: Image.Image, height: int) -> Image.Image:
    if image.height == height:
        return image
    width = round(image.width * height / image.height)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def crop_box(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> Image.Image:
    """Return the box [left, top, right, bottom] of an image.

    Box values are per-mille: 1000 spans the whole image.
    """
    width, height = image.size
    left, top, right, bottom = box
    return image.crop(
        (
            round(left / 1000 * width),
            round(top / 1000 * height),
            round(right / 1000 * width),
            round(bottom / 1000 * height),
        )
    )


def ink_coverage(
    image: Image.Image,
    boxes: list[tuple[int, int, int, int]],
) -> float:
    """Return the share of the page ink that the boxes hold.

    Box values are per-mille. Boxes that overlap are counted twice, so
    the result is capped at 1.
    """
    gray = image.convert("L")
    width, height = gray.size
    covered = 0
    for box in boxes:
        left, top, right, bottom = box
        area = (
            round(left / 1000 * width),
            round(top / 1000 * height),
            round(right / 1000 * width),
            round(bottom / 1000 * height),
        )
        covered += _ink(gray.crop(area))
    return min(1.0, covered / max(1, _ink(gray)))


# Count the pixels darker than the paper.
def _ink(image: Image.Image) -> int:
    histogram = image.histogram()
    return sum(n for value, n in enumerate(histogram) if value < INK_LEVEL)


def thumbnail(
    image: Image.Image,
    box: tuple[int, int],
) -> Image.Image:
    """Shrink an image into box, keeping its shape."""
    copy = image.copy()
    copy.thumbnail(box, Image.Resampling.LANCZOS)
    return copy
