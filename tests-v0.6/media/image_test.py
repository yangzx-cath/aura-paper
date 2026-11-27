import base64
import random

import pytest
from aura_paper.media.image import (
    crop_box,
    data_url,
    extend_sides,
    save_jpeg,
    stitch_side_by_side,
)
from PIL import Image, ImageDraw


def test_jpeg_prefix_and_payload(sample_jpeg):
    url = data_url(sample_jpeg)

    header, _, payload = url.partition(",")
    assert header == "data:image/jpeg;base64"
    assert base64.b64decode(payload) == sample_jpeg.read_bytes()


def test_png_uses_png_mime(tmp_path):
    target = tmp_path / "page.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")

    url = data_url(target)

    assert url.startswith("data:image/png;base64,")


def test_upper_suffix_uses_mime(tmp_path):
    target = tmp_path / "page.JPG"
    target.write_bytes(b"\xff\xd8fake")

    url = data_url(target)

    assert url.startswith("data:image/jpeg;base64,")


def test_unknown_suffix_raises(tmp_path):
    target = tmp_path / "page.xyz"
    target.write_bytes(b"whatever")

    with pytest.raises(ValueError, match="unsupported image type"):
        data_url(target)


def test_mirrors_the_sides_to_fill_the_frame():
    image = Image.new("RGB", (40, 60), "white")
    for x in range(40):
        colour = (x * 5, 0, 0)
        for y in range(60):
            image.putpixel((x, y), colour)

    whole = extend_sides(image, (100, 60))

    assert whole.size == (100, 60)
    # The page is centred and mirrored outward, so both seams match.
    assert whole.getpixel((30, 0)) == (0, 0, 0)
    assert whole.getpixel((69, 0)) == (195, 0, 0)
    assert whole.getpixel((29, 0)) == (0, 0, 0)
    assert whole.getpixel((70, 0)) == (195, 0, 0)


# Write a page image of the given size.
def make_page(path, size):
    Image.new("RGB", size, "white").save(path, "PNG")
    return path


def test_stitches_crops_and_saves(tmp_path):
    left = make_page(tmp_path / "left.png", (100, 150))
    right = make_page(tmp_path / "right.png", (90, 135))

    whole = stitch_side_by_side(left, right)
    assert whole.size == (200, 150)

    half = crop_box(whole, (500, 0, 1000, 1000))
    assert half.size == (100, 150)

    size = save_jpeg(half, tmp_path / "out" / "half.jpg", 92)
    assert size == (100, 150)
    with Image.open(tmp_path / "out" / "half.jpg") as saved:
        assert saved.format == "JPEG"
        assert saved.size == (100, 150)


# Fill an image with deterministic noise, so offsets differ clearly.
def make_texture(path, size):
    rng = random.Random(0)
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


def test_drops_the_shared_strip(tmp_path):
    full = make_texture(tmp_path / "full.png", (240, 120))
    with Image.open(full) as image:
        image.crop((0, 0, 140, 120)).save(tmp_path / "left.png")
        image.crop((120, 0, 240, 120)).save(tmp_path / "right.png")

    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    whole = stitch_side_by_side(left, right, max_overlap=60)

    # 140 + 120 - 20 shared pixels.
    assert whole.size == (240, 120)
