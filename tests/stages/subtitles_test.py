import json

from aura_paper.media import ffmpeg
from aura_paper.stages.subtitles import subtitles


# Write a small film, so the stage has a picture to lay subtitles over.
def make_film(path, seconds=2.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            ffmpeg.FFMPEG,
            *ffmpeg.COMMON,
            "-f",
            "lavfi",
            "-i",
            f"color=c=gray:s=320x180:d={seconds}:r=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


# Write what the jobs and compose stages would have left behind.
def make_book(root):
    book = root / "demo"
    make_film(book / "shots" / "film.mp4")
    lines = [
        {
            "index": 0,
            "kind": "旁白",
            "cast": "",
            "text": "下雨了。",
            "file": "voice/j1-0.wav",
            "start_ms": 0,
            "duration_ms": 800,
        },
        {
            "index": 1,
            "kind": "对白",
            "cast": "c1",
            "text": "我们搭城堡。",
            "file": "voice/j1-1.wav",
            "start_ms": 1000,
            "duration_ms": 800,
        },
        {
            "index": 2,
            "kind": "音效",
            "cast": "",
            "text": "哗啦",
            "file": "",
            "start_ms": 1500,
            "duration_ms": 400,
        },
    ]
    (book / "jobs.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "shots": [
                    {
                        "shot": "j1",
                        "prompt": "p",
                        "duration": 2,
                        "audio_ms": 1800,
                        "join": "硬切",
                        "lines": lines,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        "utf-8",
    )
    (book / "compose.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "film": "shots/film.mp4",
                "seconds": 2.0,
                "shots": [
                    {
                        "shot": "j1",
                        "file": "shots/j1.mp4",
                        "start": 0.0,
                        "seconds": 2.0,
                    }
                ],
                "joins": [],
            }
        ),
        "utf-8",
    )
    (book / "voice.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "shots": [
                    {
                        "shot": "j1",
                        "lines": [
                            {
                                "index": 0,
                                "kind": "旁白",
                                "text": "下雨了。",
                                "spoken": "下雨了，哗哗的。",
                                "file": "voice/j1-0.wav",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        "utf-8",
    )


def test_writes_one_cue_per_spoken_line(tmp_path):
    make_book(tmp_path)

    result = subtitles("demo", root=tmp_path, burn=False)

    assert result.error == ""
    assert result.file == "subtitles.ass"
    assert result.cues == 2
    text = (tmp_path / "demo" / "subtitles.ass").read_text("utf-8")
    assert "0:00:00.00,0:00:00.80,旁白" in text
    assert "0:00:01.00,0:00:01.80,c1" in text
    # A sound effect is heard, not read.
    assert "哗啦" not in text


def test_gives_the_narrator_and_the_cast_a_style_each(tmp_path):
    make_book(tmp_path)

    subtitles("demo", root=tmp_path, burn=False)

    text = (tmp_path / "demo" / "subtitles.ass").read_text("utf-8")
    assert "Style: 旁白,Noto Serif SC" in text
    assert "Style: c1,ZCOOL KuaiLe" in text
    assert "PlayResX: 320" in text
    assert "PlayResY: 180" in text


def test_shows_the_narration_as_it_was_read(tmp_path):
    make_book(tmp_path)

    subtitles("demo", root=tmp_path, burn=False)

    text = (tmp_path / "demo" / "subtitles.ass").read_text("utf-8")
    # The narration carries the wording it was spoken with, the dialogue
    # keeps the words printed in the book.
    assert "下雨了，哗哗的。" in text
    assert "我们搭城堡。" in text
