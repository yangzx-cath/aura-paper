from pathlib import Path

import pytest

from aura_paper.book import Book, load_book

SAMPLE_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "chicken_and_sunflower"
)


def load(**kwargs) -> Book:
    return load_book(SAMPLE_DIR, book_id="test", **kwargs)


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
    with pytest.raises(FileNotFoundError):
        load_book(tmp_path / "missing", book_id="test")


def test_empty_dir_raises(tmp_path):
    with pytest.raises(ValueError, match="no supported images"):
        load_book(tmp_path, book_id="test")


def test_load_book_uses_the_given_id():
    book = load_book(SAMPLE_DIR, book_id="C01")

    assert book.id == "C01"
    assert book.source == str(SAMPLE_DIR.resolve())


def test_load_book_defaults_to_the_directory_name():
    book = load_book(SAMPLE_DIR)

    assert book.id == SAMPLE_DIR.name


def test_pages_have_size():
    book = load()

    assert all(p.width and p.height for p in book.pages)
    # Check the exact values to catch swapped or misread dimensions.
    assert (book.pages[0].width, book.pages[0].height) == (680, 800)
    assert (book.pages[1].width, book.pages[1].height) == (1360, 800)


def test_broken_image_stops_the_load(tmp_path):
    (tmp_path / "bad.jpg").write_bytes(b"not an image")

    with pytest.raises(OSError):
        load_book(tmp_path, book_id="test")
