from PIL import Image

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
