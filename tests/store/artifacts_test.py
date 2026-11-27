import pytest

from aura_paper.store.artifacts import read_json, write_json


def test_read_json_rejects_broken_json(tmp_path):
    path = tmp_path / "book.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError):
        read_json(path)


def test_read_json_rejects_non_object_json(tmp_path):
    path = tmp_path / "book.json"
    path.write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(ValueError):
        read_json(path)


def test_write_json_accepts_str_root(tmp_path):
    root = str(tmp_path)

    path = write_json("demo", "book", {"a": 1}, root)

    assert path == tmp_path / "demo" / "book.json"


def test_write_json_defaults_to_output_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_OUTPUT_DIR", str(tmp_path / "custom"))

    path = write_json("demo", "book", {"a": 1})

    assert path == tmp_path / "custom" / "demo" / "book.json"
