import json

from PIL import Image

from aura_paper.output import write_json
from aura_paper.schema.cast import BookCast
from aura_paper.schema.location import BookLocations
from aura_paper.schema.shot import BookShots
from aura_paper.schema.voice import BookVoice
from aura_paper.stages.jobs import jobs

# A panel wider than the 2.5 the service accepts, and one it takes as is.
WIDE = (1000, 200)
SQUARE = (600, 600)


def image(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 200, 200)).save(path, quality=90)


# Write the four artifacts the jobs stage reads, plus the images they name.
def make_book(root, shots, voice_shots, size=SQUARE, master="p000_1.jpg"):
    book = root / "demo"
    image(book / "panels" / "p000_0.jpg", size)
    image(book / "panels" / "p000_1.jpg", SQUARE)
    image(book / "figures" / "p000_f0.jpg", SQUARE)

    shot_book = BookShots.from_dict(
        {"id": "demo", "style": "水彩", "shots": shots}
    )
    voice_book = BookVoice.from_dict({"id": "demo", "shots": voice_shots})
    cast_book = BookCast.from_dict(
        {
            "id": "demo",
            "cast": [
                {
                    "id": "c1",
                    "name": "小满",
                    "look": "橙背带裤",
                    "voice": "zh_female_yingtaowanzi_uranus_bigtts",
                    "pictures": ["p000_f0.jpg"],
                }
            ],
        }
    )
    places = BookLocations.from_dict(
        {
            "id": "demo",
            "style": "水彩",
            "locations": [
                {
                    "id": "l1",
                    "name": "客厅",
                    "light": "白天",
                    "master": master,
                }
            ],
            "panel_locations": [
                {"page": "p000.jpg", "panel": 0, "location": "l1"}
            ],
        }
    )
    write_json("demo", "shots", shot_book.to_dict(), root)
    write_json("demo", "voice", voice_book.to_dict(), root)
    write_json("demo", "cast", cast_book.to_dict(), root)
    write_json("demo", "locations", places.to_dict(), root)


# One shot that covers the single panel of the book.
def shot(audio, shot_id="j1"):
    return {
        "id": shot_id,
        "scene": "s1",
        "panels": [{"page": "p000.jpg", "panel": 0}],
        "cast": ["c1"],
        "camera": "中景",
        "beats": ["小满跑过来"],
        "audio": audio,
        "continuity": "",
    }


# The spoken record of one narrator line.
def spoken(index, duration_ms, shot_id="j1"):
    return {
        "shot": shot_id,
        "gap_ms": 300,
        "duration_ms": duration_ms,
        "lines": [
            {
                "index": index,
                "kind": "旁白",
                "text": "下",
                "voice": "v",
                "file": f"voice/{shot_id}-{index}.wav",
                "duration_ms": duration_ms,
            }
        ],
    }


def test_places_the_sounds_and_rounds_the_length(tmp_path):
    make_book(
        tmp_path,
        [
            shot(
                [
                    {"kind": "音效", "text": "阿嚏"},
                    {"kind": "旁白", "text": "下"},
                ]
            )
        ],
        [spoken(1, 1000)],
    )

    job = jobs(
        "demo", ratio="4:3", resolution="480p", audio=False, root=tmp_path
    ).shots[0]

    # The sound effect takes a moment, then a gap, then the line.
    assert [line.start_ms for line in job.lines] == [0, 900]
    assert [line.duration_ms for line in job.lines] == [600, 1000]
    # 1.9 s of sound plus the tail still needs four seconds of video.
    assert job.audio_ms == 1900
    assert job.duration == 4
    assert job.error == ""


def test_pads_a_panel_wider_than_the_service_takes(tmp_path):
    make_book(tmp_path, [shot([])], [], size=WIDE)

    job = jobs(
        "demo", ratio="4:3", resolution="480p", audio=False, root=tmp_path
    ).shots[0]

    panel = job.images[0].file
    assert panel.startswith("jobs/")
    width, height = Image.open(tmp_path / "demo" / panel).size
    assert round(width / height, 2) <= 2.5


def test_reports_a_shot_that_cannot_fit_the_length_limit(tmp_path):
    make_book(
        tmp_path,
        [shot([{"kind": "旁白", "text": "下"}])],
        [spoken(0, 15000)],
    )

    job = jobs(
        "demo", ratio="4:3", resolution="480p", audio=False, root=tmp_path
    ).shots[0]

    assert job.duration == 15
    assert "上限" in job.error


def test_names_the_place_and_every_reference_image(tmp_path):
    make_book(
        tmp_path,
        [shot([{"kind": "旁白", "text": "下"}])],
        [spoken(0, 1000)],
    )

    job = jobs(
        "demo", ratio="4:3", resolution="480p", audio=False, root=tmp_path
    ).shots[0]

    # One panel, one character crop and the place master, in that order.
    assert [image.note.split("，")[0] for image in job.images] == [
        "第 1 格分镜",
        "角色 小满 的参考图",
        "场地 l1 的母图",
    ]
    assert "客厅，白天" in job.prompt
    assert job.prompt.count("图2") == 1


def test_keeps_each_crop_once_when_the_place_master_is_the_panel(tmp_path):
    make_book(
        tmp_path,
        [shot([{"kind": "旁白", "text": "下"}])],
        [spoken(0, 1000)],
        master="p000_0.jpg",
    )

    job = jobs(
        "demo", ratio="4:3", resolution="480p", audio=False, root=tmp_path
    ).shots[0]

    # The master of l1 is p000_0.jpg, which is also the only panel here.
    assert [image.file for image in job.images] == [
        "panels/p000_0.jpg",
        "figures/p000_f0.jpg",
    ]


def test_writes_the_jobs_back_out(tmp_path):
    make_book(
        tmp_path,
        [shot([{"kind": "旁白", "text": "下"}])],
        [spoken(0, 1000)],
    )

    jobs("demo", ratio="4:3", resolution="480p", audio=False, root=tmp_path)

    saved = json.loads((tmp_path / "demo" / "jobs.json").read_text())

    assert saved["ratio"] == "4:3"
    assert saved["resolution"] == "480p"
    assert saved["shots"][0]["duration"] == 4
    assert saved["shots"][0]["lines"][0]["file"] == "voice/j1-0.wav"
