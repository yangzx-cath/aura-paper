import json

from aura_paper.stages.publish import publish
from aura_paper.store.books import status_of


# Write what the earlier stages would have left behind, film and all.
def make_book(root):
    book = root / "demo"
    (book / "shots").mkdir(parents=True)
    (book / "shots" / "film.mp4").write_bytes(b"film")
    (book / "subtitles.vtt").write_text("WEBVTT\n", encoding="utf-8")
    (book / "cover.jpg").write_bytes(b"cover")
    (book / "compose.json").write_text(
        json.dumps({"id": "demo", "film": "shots/film.mp4", "seconds": 3.5}),
        encoding="utf-8",
    )
    (book / "subtitles.json").write_text(
        json.dumps({"id": "demo", "cues": 2}), encoding="utf-8"
    )
    (book / "understand.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "source": "demo.pdf",
                "cover": {"title": "下雨天"},
                "pages": [{"index": 0, "filename": "p001.jpg"}],
            }
        ),
        encoding="utf-8",
    )
    (book / "cast.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "language": "zh",
                "cast": [{"id": "c1", "name": "小满"}],
            }
        ),
        encoding="utf-8",
    )
    return book


def test_packs_the_film_and_its_subtitles(tmp_path):
    make_book(tmp_path / "out")
    library = tmp_path / "books"

    result = publish("demo", root=tmp_path / "out", library=library)

    assert result.error == ""
    assert result.title == "下雨天"
    assert result.language == "zh"
    assert result.seconds == 3.5
    assert result.cues == 2
    assert [member.name for member in result.cast] == ["小满"]
    pub = library / "demo" / "pub"
    assert (pub / "film.mp4").read_bytes() == b"film"
    assert (pub / "subtitles.vtt").is_file()
    assert (pub / "cover.jpg").is_file()
    manifest = json.loads((pub / "publish.json").read_text("utf-8"))
    assert manifest["film"] == "film.mp4"
    assert manifest["vtt"] == "subtitles.vtt"
    assert status_of("demo", library) == "ready"


def test_refuses_a_book_with_no_film(tmp_path):
    book = make_book(tmp_path / "out")
    (book / "shots" / "film.mp4").unlink()
    library = tmp_path / "books"

    result = publish("demo", root=tmp_path / "out", library=library)

    assert "先跑 run_compose.py" in result.error
    assert not (library / "demo" / "pub" / "publish.json").exists()


def test_refuses_a_book_with_no_subtitles(tmp_path):
    book = make_book(tmp_path / "out")
    (book / "subtitles.vtt").unlink()
    library = tmp_path / "books"

    result = publish("demo", root=tmp_path / "out", library=library)

    assert "先跑 run_subtitles.py" in result.error
    assert not (library / "demo" / "pub" / "publish.json").exists()


# A rerun that fails leaves the release that is already there alone, so the
# shelf keeps playing the last good film.
def test_keeps_the_last_release_when_a_rerun_fails(tmp_path):
    book = make_book(tmp_path / "out")
    library = tmp_path / "books"
    publish("demo", root=tmp_path / "out", library=library)
    (book / "shots" / "film.mp4").unlink()

    result = publish("demo", root=tmp_path / "out", library=library)

    assert result.error
    assert (library / "demo" / "pub" / "publish.json").is_file()
    assert (library / "demo" / "pub" / "film.mp4").read_bytes() == b"film"
