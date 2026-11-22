"""Page image operations."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


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
) -> Image.Image:
    """Place two page images side by side and return the result.

    The shorter image is scaled to the taller one's height; nothing
    else is aligned or cropped.
    """
    left_image = load_image(left)
    right_image = load_image(right)
    height = max(left_image.height, right_image.height)
    left_image = _fit_height(left_image, height)
    right_image = _fit_height(right_image, height)

    canvas = Image.new("RGB", (left_image.width + right_image.width, height))
    canvas.paste(left_image, (0, 0))
    canvas.paste(right_image, (left_image.width, 0))
    return canvas


# Scale an image to the given height, keeping its shape.
def _fit_height(image: Image.Image, height: int) -> Image.Image:
    if image.height == height:
        return image
    width = round(image.width * height / image.height)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def crop_percent(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> Image.Image:
    """Return the percent box [left, top, right, bottom] of an image."""
    width, height = image.size
    left, top, right, bottom = box
    return image.crop(
        (
            round(left / 100 * width),
            round(top / 100 * height),
            round(right / 100 * width),
            round(bottom / 100 * height),
        )
    )


def thumbnail(
    image: Image.Image,
    box: tuple[int, int],
) -> Image.Image:
    """Shrink an image into box, keeping its shape."""
    copy = image.copy()
    copy.thumbnail(box, Image.Resampling.LANCZOS)
    return copy
