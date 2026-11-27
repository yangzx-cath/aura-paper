from aura_paper.store.artifacts import write_json


def test_str_root_is_accepted(tmp_path):
    root = str(tmp_path)

    path = write_json("demo", "book", {"a": 1}, root)

    assert path == tmp_path / "demo" / "book.json"


def test_defaults_to_output_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_OUTPUT_DIR", str(tmp_path / "custom"))

    path = write_json("demo", "book", {"a": 1})

    assert path == tmp_path / "custom" / "demo" / "book.json"
