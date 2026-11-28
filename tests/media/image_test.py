import random

import pytest
from PIL import Image, ImageDraw, UnidentifiedImageError

from aura_paper.media.image import (
    crop_image,
    image_to_url,
    load_image,
    stitch_side_by_side,
)


def test_image_to_url_uses_the_png_mime_type(tmp_path):
    target = tmp_path / "page.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")

    url = image_to_url(target)

    assert url.startswith("data:image/png;base64,")


def test_image_to_url_reads_an_upper_case_suffix(tmp_path):
    target = tmp_path / "page.JPG"
    target.write_bytes(b"\xff\xd8fake")

    url = image_to_url(target)

    assert url.startswith("data:image/jpeg;base64,")


def test_image_to_url_rejects_an_unknown_suffix(tmp_path):
    target = tmp_path / "page.xyz"
    target.write_bytes(b"whatever")

    with pytest.raises(ValueError, match="unsupported image type"):
        image_to_url(target)


def test_load_image_rejects_a_file_that_is_not_an_image(tmp_path):
    target = tmp_path / "page.jpg"
    target.write_bytes(b"not an image")

    with pytest.raises(UnidentifiedImageError):
        load_image(target)


def test_crop_image_rounds_the_box_edges():
    image = Image.new("RGB", (3, 4), "white")

    left = crop_image(image, (0, 0, 500, 1000))
    right = crop_image(image, (500, 0, 1000, 1000))

    assert left.size == (2, 4)
    assert right.size == (1, 4)


def make_texture(path, size, seed):
    rng = random.Random(seed)
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for _ in range(300):
        x = rng.randrange(size[0])
        y = rng.randrange(size[1])
        width = rng.randrange(2, 12)
        height = rng.randrange(2, 20)
        colour = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        draw.rectangle((x, y, x + width, y + height), fill=colour)
    image.save(path)
    return path


def test_stitch_side_by_side_drops_the_shared_strip(tmp_path):
    full = make_texture(tmp_path / "full.png", (240, 120), 0)
    with Image.open(full) as image:
        image.crop((0, 0, 140, 120)).save(tmp_path / "left.png")
        image.crop((120, 0, 240, 120)).save(tmp_path / "right.png")

    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    whole = stitch_side_by_side(left, right, max_overlap=60)

    # 140 + 120 pixels, less the 20 the two pages share at the fold.
    assert whole.size == (240, 120)


def test_stitch_side_by_side_keeps_pages_without_a_shared_strip(tmp_path):
    left = make_texture(tmp_path / "left.png", (100, 120), 1)
    right = make_texture(tmp_path / "right.png", (120, 120), 2)

    whole = stitch_side_by_side(left, right, max_overlap=60)

    assert whole.size == (220, 120)
