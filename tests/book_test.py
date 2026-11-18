from pathlib import Path

import pytest

from aura_paper.book import load_book


def test_load_sample_dir(sample_book):
    book = load_book(sample_book, book_id="test")

    assert book.page_count == 19
    assert [p.index for p in book.pages] == list(range(19))
    assert book.pages[0].filename == "01.jpg"
    assert book.pages[-1].filename == "19.jpg"
    assert book.source == str(sample_book.resolve())
    assert all(Path(p.path).is_absolute() for p in book.pages)


def test_a_wide_scan_is_a_spread(sample_book):
    book = load_book(sample_book, book_id="test")
    kinds = [(p.width, p.height, p.kind) for p in book.pages[:2]]

    assert kinds == [(680, 800, "portrait"), (1360, 800, "landscape")]


def test_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_book(tmp_path / "missing", book_id="test")


def test_empty_dir_raises(tmp_path):
    with pytest.raises(ValueError, match="no supported images"):
        load_book(tmp_path, book_id="test")


def test_load_book_uses_the_given_id(sample_book):
    book = load_book(sample_book, book_id="C01")

    assert book.id == "C01"
    assert book.source == str(sample_book.resolve())


def test_load_book_defaults_to_the_directory_name(sample_book):
    book = load_book(sample_book)

    assert book.id == sample_book.name


def test_pages_have_size(sample_book):
    book = load_book(sample_book, book_id="test")

    assert all(p.width and p.height for p in book.pages)
    # Check the exact values to catch swapped or misread dimensions.
    assert (book.pages[0].width, book.pages[0].height) == (680, 800)
    assert (book.pages[1].width, book.pages[1].height) == (1360, 800)


def test_broken_image_stops_the_load(tmp_path):
    (tmp_path / "bad.jpg").write_bytes(b"not an image")

    with pytest.raises(OSError):
        load_book(tmp_path, book_id="test")
