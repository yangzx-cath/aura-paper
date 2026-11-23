import json

from aura_paper.store.output import write_json


def test_json_puts_the_file_under_book_id(tmp_path):
    path = write_json("demo", "book", {"a": 1}, tmp_path)

    assert path == tmp_path / "demo" / "book.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}


def test_json_creates_missing_directories(tmp_path):
    root = tmp_path / "a" / "b"

    path = write_json("demo", "book", {"a": 1}, root)

    assert path.parent.is_dir()


def test_json_keeps_chinese_readable(tmp_path):
    path = write_json("demo", "book", {"title": "小鸡球球"}, tmp_path)

    text = path.read_text(encoding="utf-8")
    assert "小鸡球球" in text
    assert text.endswith("\n")


def test_json_overwrites_the_previous_file(tmp_path):
    write_json("demo", "book", {"title": "旧"}, tmp_path)

    path = write_json("demo", "book", {"title": "新"}, tmp_path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "新"


def test_json_defaults_to_out_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_OUT_DIR", str(tmp_path / "custom"))

    path = write_json("demo", "book", {"a": 1})

    assert path == tmp_path / "custom" / "demo" / "book.json"
