import io
import json

import pytest

from aura_paper.store.books import (
    STAGE_RUNS_NAME,
    TITLE_FROM_USER,
    import_pdf,
    read_book_meta,
    set_title,
    status_of,
)

PDF = b"%PDF-1.4\n" + b"x" * 32


def test_import_pdf_rejects_a_name_that_is_not_pdf(tmp_path):
    with pytest.raises(ValueError):
        import_pdf(io.BytesIO(PDF), "book.jpg", root=tmp_path)


def test_import_pdf_rejects_a_stream_without_a_pdf_header(tmp_path):
    with pytest.raises(ValueError):
        import_pdf(io.BytesIO(b"x" * 64), "book.pdf", root=tmp_path)


def test_import_pdf_removes_the_folder_when_it_fails(tmp_path):
    with pytest.raises(ValueError):
        import_pdf(io.BytesIO(b"x" * 64), "book.pdf", root=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_import_pdf_does_not_reuse_a_free_id(tmp_path):
    (tmp_path / "B002").mkdir()

    meta = import_pdf(io.BytesIO(PDF), "a.pdf", root=tmp_path)

    assert meta.id == "B003"


def test_set_title_keeps_a_title_typed_in_by_hand(tmp_path):
    meta = import_pdf(io.BytesIO(PDF), "a.pdf", root=tmp_path)
    set_title(meta.id, "手工名", source=TITLE_FROM_USER, root=tmp_path)

    kept = set_title(meta.id, "自动名", root=tmp_path)
    after = read_book_meta(meta.id, tmp_path)

    assert kept is False
    assert after.title == "手工名"


def test_status_of_prefers_a_running_stage(tmp_path):
    meta = import_pdf(io.BytesIO(PDF), "a.pdf", root=tmp_path)
    runs = tmp_path / meta.id / STAGE_RUNS_NAME
    runs.write_text(
        json.dumps({"crop": {"state": "running"}}), encoding="utf-8"
    )

    assert status_of(meta.id, tmp_path) == "running"
