"""Detect the printed text on a page and fill it out of a crop."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# One text line as its corner points, in page pixels.
Poly = list[tuple[float, float]]

# Detection only: the direction classifier and the recognizer are skipped.
PARAMS = {"use_det": True, "use_cls": False, "use_rec": False}

# The colour around a line is read this many pixels out from its mask.
RING = 14

# The mask edge fades over this many pixels.
FEATHER = 2

# A blend is worked out this many pixels past the mask.
PAD = 10

# A copy is taken this many pixels past the line it replaces.
PATCH_GAP = 6

# A copy is looked for at these multiples of one line and one line width.
PATCH_STEPS = (1, 2, 3, 4)

# The engine is built once, because building it loads three model files.
_engine = None


def text_boxes(path: str | Path) -> list[Poly]:
    """Return one four-point box per printed line, in page pixels."""
    result = _build_engine()(str(path), **PARAMS)
    boxes = result.boxes
    if boxes is None:
        return []
    return _as_polys(boxes)


# Build the reader on first use and keep it for the next page.
def _build_engine():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR

        _engine = RapidOCR()
    return _engine


# Drop the numpy wrapper the reader returns.
def _as_polys(boxes) -> list[Poly]:
    polys = []
    for box in boxes:
        poly = []
        for x, y in box:
            poly.append((float(x), float(y)))
        polys.append(poly)
    return polys


def page_array(image: Image.Image) -> np.ndarray:
    """Return the page as a BGR array, which is what the fill reads."""
    return np.ascontiguousarray(np.asarray(image)[:, :, ::-1])


def crop_without_text(
    page: np.ndarray,
    box: list[int],
    text: list[Poly],
    *,
    margin: int,
    flat_limit: float,
) -> Image.Image:
    """Return the box of the page, per-mille, with its text filled in.

    The page is a BGR array from page_array. Text boxes are in page
    pixels. The mask around a line grows by margin pixels. A line whose
    surroundings differ by less than flat_limit takes their colour; the
    rest of the lines are filled from their neighbours.
    """
    height, width = page.shape[:2]
    left, top, right, bottom = _pixels(box, (width, height))
    region = page[top:bottom, left:right].copy()
    local = _moved(text, (left, top))
    if not local:
        return Image.fromarray(region[:, :, ::-1])
    return _filled(region, local, margin, flat_limit)


# Turn a per-mille box into the pixel rectangle crop_box would cut.
def _pixels(
    box: list[int],
    size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = size
    left, top, right, bottom = box
    return (
        round(left / 1000 * width),
        round(top / 1000 * height),
        round(right / 1000 * width),
        round(bottom / 1000 * height),
    )


# Move page boxes into the coordinates of the crop.
def _moved(text: list[Poly], origin: tuple[int, int]) -> list[Poly]:
    left, top = origin
    moved = []
    for poly in text:
        moved.append([(x - left, y - top) for x, y in poly])
    return moved


# Fill each line from the paper beside it, the rest by inpainting.
def _filled(
    region: np.ndarray,
    text: list[Poly],
    margin: int,
    flat_limit: float,
) -> Image.Image:
    filled = region.copy()
    masks = _masks(region.shape[:2], text, margin)
    whole = _union(region.shape[:2], masks)
    rough = np.zeros(region.shape[:2], dtype=np.uint8)
    for mask in masks:
        pixels = _around(region, mask, flat_limit)
        if pixels is None:
            rough[mask > 0] = 255
            continue
        _patch(filled, region, mask, pixels, whole, flat_limit)
    if cv2.countNonZero(rough):
        patched = cv2.inpaint(filled, rough, margin, cv2.INPAINT_TELEA)
        filled[rough > 0] = patched[rough > 0]
    return Image.fromarray(filled[:, :, ::-1])


# Cut one mask per line.
def _masks(
    shape: tuple[int, int],
    text: list[Poly],
    margin: int,
) -> list[np.ndarray]:
    masks = []
    for poly in text:
        masks.append(_line_mask(shape, poly, margin))
    return masks


# Cover every line with one mask.
def _union(shape: tuple[int, int], masks: list[np.ndarray]) -> np.ndarray:
    whole = np.zeros(shape, dtype=np.uint8)
    for mask in masks:
        cv2.bitwise_or(whole, mask, whole)
    return whole


# Copy paper from beside one line, then fade the copy into the paper.
def _patch(
    filled: np.ndarray,
    region: np.ndarray,
    mask: np.ndarray,
    pixels: np.ndarray,
    whole: np.ndarray,
    flat_limit: float,
) -> None:
    ys, xs = np.nonzero(mask)
    source = _shifted(filled, whole, ys, xs, pixels, flat_limit)
    if source is None:
        source = np.median(pixels, axis=0).astype(np.uint8)
    filled[ys, xs] = source
    _soften(filled, region, mask, ys, xs)


# Return the pixels one clean shift of the line holds, or nothing.
def _shifted(
    filled: np.ndarray,
    whole: np.ndarray,
    ys: np.ndarray,
    xs: np.ndarray,
    pixels: np.ndarray,
    flat_limit: float,
) -> np.ndarray | None:
    height, width = whole.shape[:2]
    tall = int(ys.max() - ys.min()) + PATCH_GAP
    wide = int(xs.max() - xs.min()) + PATCH_GAP
    for step in PATCH_STEPS:
        for dy, dx in (
            (step * tall, 0),
            (-step * tall, 0),
            (0, step * wide),
            (0, -step * wide),
        ):
            sy = ys + dy
            sx = xs + dx
            if sy.min() < 0 or sy.max() >= height:
                continue
            if sx.min() < 0 or sx.max() >= width:
                continue
            if whole[sy, sx].any():
                continue
            values = filled[sy, sx]
            if _even(values, pixels, flat_limit):
                return values
    return None


# Tell whether these pixels look like the paper the line sits on.
def _even(values: np.ndarray, pixels: np.ndarray, flat_limit: float) -> bool:
    flat = values.astype(np.float32)
    if float(np.mean(np.std(flat, axis=0))) >= flat_limit:
        return False
    apart = np.abs(np.mean(flat, axis=0) - np.mean(pixels, axis=0))
    return float(np.max(apart)) < flat_limit


# Fade the copy into the paper around the line.
def _soften(
    filled: np.ndarray,
    region: np.ndarray,
    mask: np.ndarray,
    ys: np.ndarray,
    xs: np.ndarray,
) -> None:
    top = max(0, int(ys.min()) - PAD)
    bottom = int(ys.max()) + PAD
    left = max(0, int(xs.min()) - PAD)
    right = int(xs.max()) + PAD
    before = region[top:bottom, left:right].astype(np.float32)
    after = filled[top:bottom, left:right].astype(np.float32)
    small = mask[top:bottom, left:right].astype(np.float32) / 255.0
    alpha = cv2.GaussianBlur(small, (0, 0), FEATHER)[:, :, None]
    mixed = before * (1.0 - alpha) + after * alpha
    filled[top:bottom, left:right] = np.clip(mixed, 0, 255).astype(np.uint8)


# Paint one line and grow the paint by margin pixels.
def _line_mask(
    shape: tuple[int, int],
    poly: Poly,
    margin: int,
) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    points = np.round(poly).astype(np.int32)
    cv2.fillPoly(mask, [points], 255)
    size = margin * 2 + 1
    return cv2.dilate(mask, np.ones((size, size), dtype=np.uint8))


# Return the pixels around a line when their colour is nearly flat.
def _around(
    region: np.ndarray,
    mask: np.ndarray,
    flat_limit: float,
) -> np.ndarray | None:
    ring = cv2.dilate(mask, np.ones((RING * 2 + 1,) * 2, dtype=np.uint8))
    ring = cv2.bitwise_and(ring, cv2.bitwise_not(mask))
    pixels = region[ring > 0]
    if len(pixels) < 40:
        return None
    spread = np.std(pixels.astype(np.float32), axis=0)
    if float(np.mean(spread)) >= flat_limit:
        return None
    return pixels
