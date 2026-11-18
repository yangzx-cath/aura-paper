"""Fixtures that build the page images the tests need."""

import pytest
from PIL import Image

# Real scans cannot ship with the tests, so a plain portrait book stands in,
# with the second page scanned as a wide spread.
PAGE_COUNT = 19
PORTRAIT_SIZE = (680, 800)
LANDSCAPE_SIZE = (1360, 800)
SPREAD_PAGE = 2


@pytest.fixture
def sample_book(tmp_path):
    folder = tmp_path / "sample_book"
    folder.mkdir()
    for index in range(1, PAGE_COUNT + 1):
        size = LANDSCAPE_SIZE if index == SPREAD_PAGE else PORTRAIT_SIZE
        Image.new("RGB", size, "white").save(folder / f"{index:02d}.jpg")
    return folder


@pytest.fixture
def sample_jpeg(tmp_path):
    path = tmp_path / "page.jpg"
    Image.new("RGB", PORTRAIT_SIZE, "white").save(path)
    return path
