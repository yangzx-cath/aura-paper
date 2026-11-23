"""Fixtures that build the page images the tests need."""

import pytest
from PIL import Image

# Real scans cannot ship with the tests, so a plain portrait stands in.
PORTRAIT_SIZE = (680, 800)


@pytest.fixture
def sample_jpeg(tmp_path):
    path = tmp_path / "page.jpg"
    Image.new("RGB", PORTRAIT_SIZE, "white").save(path)
    return path
