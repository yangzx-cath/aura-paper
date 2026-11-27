import json

from aura_paper.clients.llm import LLMClient, LLMError
from aura_paper.schema.content import BookContent
from aura_paper.stages.assets import assets
from aura_paper.stages.crop import crop
from aura_paper.store.cache import Cache
from aura_paper.store.output import write_json
from PIL import Image

CAST = {
    "cast": [
        {
            "key": "A",
            "name": "小满",
            "look": "橙色背带裤",
            "best": "p000_f0.jpg",
        }
    ],
    "figure_cast": [
        {"file": "p000_f0.jpg", "key": "A"},
        {"file": "p000_f1.jpg", "key": "A"},
    ],
    "resolved": [
        {
            "page": 1,
            "issue": "谁在跑",
            "answer": "小满",
            "evidence": "同一件背带裤",
        }
    ],
    "open": [],
}

LOCATIONS = {
    "locations": [
        {
            "key": "L1",
            "name": "客厅",
            "light": "白天",
            "master": "p000_0.jpg",
        },
        {
            "key": "L2",
            "name": "花园",
            "light": "夜晚",
            "master": "p000_1.jpg",
        },
    ],
    "panel_locations": [
        {"page": "p000.jpg", "panel": 0, "key": "L1"},
        {"page": "p000.jpg", "panel": 1, "key": "L2"},
    ],
    "style": "水彩",
}


# Reply with fixed answers, chosen by which question the prompt asks.
class FakeLLM(LLMClient):
    def __init__(self, cast, locations=None, model="fake-model"):
        super().__init__("http://example/v1", "test-key", model)
        self.cast = cast
        self.locations = locations or {}
        self.calls = 0

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        self.calls += 1
        if "【人物裁图】" in prompt:
            return json.dumps(self.cast)
        return json.dumps(self.locations)


# Fail every call, the way an unreachable endpoint does.
class BrokenLLM(LLMClient):
    def __init__(self):
        super().__init__("http://example/v1", "test-key", "fake-model")

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        raise LLMError("endpoint down")


# Answer the cast question, then fail the place question.
class PlacesBrokenLLM(FakeLLM):
    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        if "【人物裁图】" in prompt:
            return super().chat(prompt, images=images)
        raise LLMError("locations down")


# Answer every call with the same text, whatever was asked.
class RawLLM(LLMClient):
    def __init__(self, reply):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.reply = reply

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        return self.reply


# Describe one figure with a per-mille box.
def figure(box, facing="正面", view="全身", occlusion="无"):
    return {
        "name": "小满",
        "body": "小女孩",
        "outfit": "粉色上衣",
        "view": view,
        "facing": facing,
        "occlusion": occlusion,
        "box": box,
    }


# Write an understand record and the page images it points at.
def make_book(root, pages):
    folder = root / "demo"
    folder.mkdir()
    images = folder / "pages"
    images.mkdir()
    records = []
    for index, page in enumerate(pages):
        name = f"p{index:03d}.jpg"
        Image.new("RGB", (100, 120), "white").save(images / name)
        records.append(
            {
                "index": index,
                "filename": name,
                "width": 100,
                "height": 120,
                "panels": page.get("panels", []),
                "figures": page.get("figures", []),
            }
        )
    book = BookContent.from_dict({"id": "demo", "pages": records})
    write_json("demo", "understand", book.to_dict(), root)
    crop("demo", root=root)


def test_groups_crops_into_cast_and_locations(tmp_path):
    pages = [
        {
            "panels": [
                {"box": [0, 0, 800, 800], "description": "客厅"},
                {"box": [0, 0, 200, 200], "description": "特写"},
            ],
            "figures": [
                figure([0, 0, 300, 700], facing="侧面"),
                figure([400, 0, 700, 700]),
            ],
        }
    ]
    make_book(tmp_path, pages)
    llm = FakeLLM(CAST, LOCATIONS)

    cast_book, places = assets("demo", llm=llm, root=tmp_path)

    assert [member.id for member in cast_book.cast] == ["c1"]
    assert cast_book.cast[0].name == "小满"
    # The rank order puts p000_f1.jpg first, the model pick moves it back.
    assert cast_book.cast[0].pictures == ["p000_f0.jpg", "p000_f1.jpg"]
    assert cast_book.resolved[0].answer == "小满"
    owners = sorted((item.file, item.cast) for item in cast_book.figure_cast)
    assert owners == [
        ("p000_f0.jpg", "c1"),
        ("p000_f1.jpg", "c1"),
    ]
    # p000_1.jpg is a close-up, so it cannot be a place master.
    assert [place.master for place in places.locations] == [
        "p000_0.jpg",
        "",
    ]
    owned = [(item.panel, item.location) for item in places.panel_locations]
    assert owned == [(0, "l1"), (1, "l2")]
    assert places.style == "水彩"
    assert (tmp_path / "demo" / "cast.json").is_file()
    assert (tmp_path / "demo" / "locations.json").is_file()
    assert llm.calls == 2


def test_keeps_two_pictures_and_ignores_a_pick_it_does_not_own(tmp_path):
    pages = [
        {
            "figures": [
                figure([0, 0, 300, 700]),
                figure([400, 0, 600, 700]),
            ]
        },
        {
            "figures": [
                figure([0, 0, 250, 600]),
                figure([400, 0, 600, 600]),
            ]
        },
    ]
    make_book(tmp_path, pages)
    reply = {
        "cast": [
            {"key": "A", "name": "甲", "look": "红衣", "best": "p001_f0.jpg"},
            {"key": "B", "name": "乙", "look": "蓝衣", "best": "p001_f0.jpg"},
            "junk",
        ],
        "figure_cast": [
            {"file": "p000_f0.jpg", "key": "A"},
            {"file": "p000_f1.jpg", "key": "A"},
            {"file": "p001_f1.jpg", "key": "A"},
            {"file": "p001_f0.jpg", "key": "B"},
        ],
    }
    llm = FakeLLM(reply)

    cast_book, _ = assets("demo", llm=llm, root=tmp_path)

    # A owns three crops, so only its two best stay.
    assert [member.id for member in cast_book.cast] == ["c1", "c2"]
    assert cast_book.cast[0].pictures == ["p000_f0.jpg", "p000_f1.jpg"]
    assert cast_book.cast[1].pictures == ["p001_f0.jpg"]


def test_records_a_failed_call_in_both_files(tmp_path):
    pages = [
        {
            "panels": [{"box": [0, 0, 800, 800], "description": "客厅"}],
            "figures": [figure([0, 0, 300, 700])],
        }
    ]
    make_book(tmp_path, pages)

    cast_book, places = assets("demo", llm=BrokenLLM(), root=tmp_path)

    assert "endpoint down" in cast_book.error
    assert "endpoint down" in places.error
    assert cast_book.cast == []
    assert (tmp_path / "demo" / "cast.json").is_file()
    assert (tmp_path / "demo" / "locations.json").is_file()


def test_reports_an_empty_cast(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)
    llm = FakeLLM({"cast": []})

    cast_book, _ = assets("demo", llm=llm, root=tmp_path)

    assert cast_book.cast == []
    assert cast_book.error == "model returned no cast"


def test_writes_empty_files_for_a_book_without_content(tmp_path):
    make_book(tmp_path, [{}])
    llm = FakeLLM(CAST)

    cast_book, places = assets("demo", llm=llm, root=tmp_path)

    assert llm.calls == 0
    assert cast_book.cast == []
    assert places.locations == []
    assert cast_book.error == ""
    assert places.error == ""
    assert (tmp_path / "demo" / "cast.json").is_file()
    assert (tmp_path / "demo" / "locations.json").is_file()


def test_reuses_the_cached_answer(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)
    llm = FakeLLM(CAST)
    cache_dir = tmp_path / "cache"

    first, _ = assets("demo", llm=llm, root=tmp_path, cache=Cache(cache_dir))
    second, _ = assets("demo", llm=llm, root=tmp_path, cache=Cache(cache_dir))

    assert llm.calls == 1
    assert second.error == ""
    assert second.cast == first.cast
    assert (cache_dir / "assets" / "demo").is_dir()


def test_asks_again_when_the_model_changes(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)
    cache_dir = tmp_path / "cache"
    first = FakeLLM(CAST)
    other = FakeLLM(CAST, model="other-model")

    assets("demo", llm=first, root=tmp_path, cache=Cache(cache_dir))
    cast_book, _ = assets(
        "demo", llm=other, root=tmp_path, cache=Cache(cache_dir)
    )

    assert first.calls == 1
    assert other.calls == 1
    assert cast_book.model == "other-model"


def test_records_each_error_in_its_own_file(tmp_path):
    pages = [
        {
            "panels": [{"box": [0, 0, 800, 800], "description": "客厅"}],
            "figures": [figure([0, 0, 300, 700])],
        }
    ]
    make_book(tmp_path, pages)

    cast_book, places = assets("demo", llm=BrokenLLM(), root=tmp_path)

    assert cast_book.error == "endpoint down"
    assert places.error == "endpoint down"


def test_keeps_the_cast_when_only_the_place_call_fails(tmp_path):
    pages = [
        {
            "panels": [{"box": [0, 0, 800, 800], "description": "客厅"}],
            "figures": [figure([0, 0, 300, 700])],
        }
    ]
    make_book(tmp_path, pages)

    cast_book, places = assets(
        "demo", llm=PlacesBrokenLLM(CAST), root=tmp_path
    )

    assert [member.name for member in cast_book.cast] == ["小满"]
    assert cast_book.error == ""
    assert places.locations == []
    assert places.error == "locations down"


def test_records_a_reply_that_is_not_json(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)

    cast_book, _ = assets(
        "demo", llm=RawLLM("抱歉，我看不清。"), root=tmp_path
    )

    assert cast_book.cast == []
    assert "no JSON object found" in cast_book.error


def test_reads_panel_numbers_and_leaves_unknown_places_empty(tmp_path):
    pages = [
        {
            "panels": [
                {"box": [0, 0, 800, 800], "description": "客厅"},
                {"box": [0, 0, 900, 900], "description": "花园"},
                {"box": [0, 0, 950, 950], "description": "门口"},
            ]
        }
    ]
    make_book(tmp_path, pages)
    reply = {
        "locations": [
            {
                "key": "L1",
                "name": "客厅",
                "light": "白天",
                "master": "",
            }
        ],
        "panel_locations": [
            {"page": "p000.jpg", "panel": "0", "key": "L1"},
            {"page": "p000.jpg", "panel": 1, "key": "没这个标签"},
            {"page": "p000.jpg", "panel": None, "key": "L1"},
            # A page outside the book cannot take a place.
            {"page": "p999.jpg", "panel": 0, "key": "L1"},
            "junk",
        ],
        "style": " 水彩 ",
    }

    _, places = assets("demo", llm=FakeLLM({}, reply), root=tmp_path)

    owned = [(item.panel, item.location) for item in places.panel_locations]
    assert owned == [(0, "l1"), (1, ""), (2, "")]
    assert places.locations[0].master == ""
    assert places.style == "水彩"


def test_leaves_a_crop_of_an_unknown_character_unowned(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)
    reply = {
        "cast": [{"key": "A", "name": "小满", "look": "红衣"}],
        "figure_cast": [{"file": "p000_f0.jpg", "key": "没这个标签"}],
    }

    cast_book, _ = assets("demo", llm=FakeLLM(reply), root=tmp_path)

    assert cast_book.figure_cast[0].cast == ""
    assert cast_book.cast[0].pictures == []
    assert cast_book.unpictured == cast_book.cast


def test_reports_an_empty_place_list(tmp_path):
    pages = [{"panels": [{"box": [0, 0, 800, 800], "description": "客厅"}]}]
    make_book(tmp_path, pages)

    _, places = assets(
        "demo", llm=FakeLLM({}, {"style": "水彩"}), root=tmp_path
    )

    assert places.locations == []
    assert places.error == "model returned no location"


def test_reports_an_empty_style(tmp_path):
    pages = [{"panels": [{"box": [0, 0, 800, 800], "description": "客厅"}]}]
    make_book(tmp_path, pages)
    reply = {
        "locations": [{"key": "L1", "name": "客厅", "light": "白天"}],
        "panel_locations": [{"page": "p000.jpg", "panel": 0, "key": "L1"}],
    }

    _, places = assets("demo", llm=FakeLLM({}, reply), root=tmp_path)

    assert places.locations[0].id == "l1"
    assert places.error == "model returned no style"


def test_reports_the_place_errors_on_their_own(tmp_path):
    pages = [
        {
            "panels": [{"box": [0, 0, 800, 800], "description": "客厅"}],
            "figures": [figure([0, 0, 300, 700])],
        }
    ]
    make_book(tmp_path, pages)

    cast_book, places = assets(
        "demo", llm=FakeLLM({"cast": []}, {}), root=tmp_path
    )

    assert cast_book.error == "model returned no cast"
    assert places.error == (
        "model returned no location；model returned no style"
    )
