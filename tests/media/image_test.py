import random

from PIL import Image, ImageDraw

from aura_paper.media.image import (
    crop_percent,
    save_jpeg,
    stitch_side_by_side,
)


# Write a page image of the given size.
def make_page(path, size):
    Image.new("RGB", size, "white").save(path, "PNG")
    return path


def test_stitches_crops_and_saves(tmp_path):
    left = make_page(tmp_path / "left.png", (100, 150))
    right = make_page(tmp_path / "right.png", (90, 135))

    whole = stitch_side_by_side(left, right)
    assert whole.size == (200, 150)

    half = crop_percent(whole, (50, 0, 100, 100))
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
