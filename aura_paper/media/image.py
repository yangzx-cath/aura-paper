"""Page image processing."""

import base64
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

# Supported image suffixes and MIME types.
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# Pixels between the seam widths that get compared.
SEAM_STEP = 2

# A real overlap matches far better than this mean colour difference.
SEAM_LIMIT = 12.0


def image_to_url(path: str | Path) -> str:
    """Convert an image file to a data URL."""
    target = Path(path)
    mime = IMAGE_MIME_TYPES.get(target.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported image type: {target.suffix}")

    raw = target.read_bytes()
    payload = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{payload}"


def load_image(path: str | Path) -> Image.Image:
    """Open an image file as RGB."""
    with Image.open(path) as image:
        return image.convert("RGB")


def save_jpeg(
    image: Image.Image,
    path: str | Path,
    quality: int,
) -> tuple[int, int]:
    """Write an RGB JPEG and return its width and height."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(target, "JPEG", quality=quality, optimize=True)
    return image.size


def make_thumbnail(
    image: Image.Image,
    box: tuple[int, int],
) -> Image.Image:
    """Shrink an image into box, keeping its shape."""
    copy = image.copy()
    copy.thumbnail(box, Image.Resampling.LANCZOS)
    return copy


def crop_image(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> Image.Image:
    """Cut one box out of an image.

    Box values go up to 1000, which spans the whole image.
    """
    width, height = image.size
    left, top, right, bottom = box
    area = (
        round(left / 1000 * width),
        round(top / 1000 * height),
        round(right / 1000 * width),
        round(bottom / 1000 * height),
    )
    return image.crop(area)


def stitch_side_by_side(
    left: str | Path,
    right: str | Path,
    max_overlap: int = 0,
) -> Image.Image:
    """Place two page images side by side and return the result.

    The shorter image is scaled to the taller one's height. Up to
    max_overlap pixels shared at the fold are dropped.
    """
    left_image = load_image(left)
    right_image = load_image(right)
    if max_overlap > 0:
        overlap = _seam_overlap(left_image, right_image, max_overlap)
        if overlap > 0:
            width = right_image.width
            height = right_image.height
            right_image = right_image.crop((overlap, 0, width, height))

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


# Scale an image to the given height, keeping its shape.
def _fit_height(image: Image.Image, height: int) -> Image.Image:
    if image.height == height:
        return image
    width = round(image.width * height / image.height)
    return image.resize((width, height), Image.Resampling.LANCZOS)
