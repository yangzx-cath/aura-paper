from pathlib import Path

import pytest

from book import Book

SAMPLE_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "chicken_and_sunflower"
)


def load(**kwargs) -> Book:
    book = Book("test")
    book.load(SAMPLE_DIR, **kwargs)
    return book


def test_load_sample_dir():
    book = load()

    assert book.page_count == 19
    assert [p.index for p in book.pages] == list(range(19))
    assert book.pages[0].filename == "01.jpg"
    assert book.pages[-1].filename == "19.jpg"
    assert book.source == str(SAMPLE_DIR.resolve())
    assert all(Path(p.path).is_absolute() for p in book.pages)
    assert all(p.kind == "single" for p in book.pages)


def test_kinds_override():
    book = load(default_kind="spread", kinds={"02.jpg": "single"})
    kinds = {p.filename: p.kind for p in book.pages}

    assert kinds["02.jpg"] == "single"
    assert kinds["01.jpg"] == "spread"


def test_unknown_filename_raises():
    with pytest.raises(ValueError, match="unknown page filenames"):
        load(kinds={"nope.jpg": "spread"})


def test_invalid_kind_raises():
    with pytest.raises(ValueError, match="invalid kind"):
        load(kinds={"01.jpg": "wide"})


def test_non_filename_key_raises():
    with pytest.raises(ValueError, match="must be a filename"):
        load(kinds={1: "spread"})


def test_missing_source_raises(tmp_path):
    book = Book("test")
    with pytest.raises(FileNotFoundError):
        book.load(tmp_path / "missing")


def test_empty_dir_raises(tmp_path):
    book = Book("test")
    with pytest.raises(ValueError, match="no supported images"):
        book.load(tmp_path)


def test_load_twice_raises_and_keeps_pages():
    book = load()

    with pytest.raises(RuntimeError, match="already loaded"):
        book.load(SAMPLE_DIR)

    assert book.page_count == 19


def test_pages_have_size():
    book = load()

    assert all(p.width and p.height for p in book.pages)
    # Check the exact values to catch swapped or misread dimensions.
    assert (book.pages[0].width, book.pages[0].height) == (680, 800)
    assert (book.pages[1].width, book.pages[1].height) == (1360, 800)


def test_broken_image_has_no_size(tmp_path):
    (tmp_path / "bad.jpg").write_bytes(b"not an image")

    book = Book("test")
    book.load(tmp_path)

    assert book.page_count == 1
    assert book.pages[0].width is None
    assert book.pages[0].height is None
