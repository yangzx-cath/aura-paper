import json

from PIL import Image

from aura_paper.cache import Cache
from aura_paper.clients.llm import LLMClient, LLMError
from aura_paper.output import write_json
from aura_paper.schema.content import BookContent
from aura_paper.stages.assets import assets, pick_figures

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

    result = assets("demo", llm=llm, root=tmp_path)

    assert [member.id for member in result.cast] == ["c1"]
    assert result.cast[0].name == "小满"
    # The rank order puts p000_f1.jpg first, the model pick moves it back.
    assert result.cast[0].pictures == ["p000_f0.jpg", "p000_f1.jpg"]
    assert result.resolved[0].answer == "小满"
    owners = sorted((item.file, item.cast) for item in result.figure_cast)
    assert owners == [
        ("p000_f0.jpg", "c1"),
        ("p000_f1.jpg", "c1"),
    ]
    # p000_1.jpg is a close-up, so it cannot be a place master.
    assert [place.master for place in result.locations] == [
        "p000_0.jpg",
        "",
    ]
    places = [(item.panel, item.location) for item in result.panel_locations]
    assert places == [(0, "l1"), (1, "l2")]
    assert result.style == "水彩"
    assert llm.calls == 2


def test_keeps_only_figures_that_can_stand_alone(tmp_path):
    pages = [
        {
            "figures": [
                figure([0, 0, 200, 250]),
                figure([500, 0, 699, 251]),
                figure([0, 400, 300, 700], view="半身"),
                figure([400, 400, 700, 700], facing="背面"),
                figure([700, 400, 1000, 700], occlusion="遮挡"),
                # A sibling without a box cannot overlap anything.
                figure([0, 0, 0, 0]),
            ]
        },
        {
            "figures": [
                figure([0, 0, 100, 1000]),
                figure([69, 0, 169, 1000]),
                figure([400, 0, 600, 1000]),
            ]
        },
        {
            "figures": [
                figure([0, 0, 100, 1000]),
                figure([70, 0, 170, 1000]),
            ]
        },
    ]
    make_book(tmp_path, pages)

    picks = pick_figures("demo", root=tmp_path)

    assert sorted(pick.file for pick in picks) == [
        "p000_f0.jpg",
        "p001_f2.jpg",
        "p002_f0.jpg",
        "p002_f1.jpg",
    ]


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

    result = assets("demo", llm=llm, root=tmp_path)

    # A owns three crops, so only its two best stay.
    assert [member.id for member in result.cast] == ["c1", "c2"]
    assert result.cast[0].pictures == ["p000_f0.jpg", "p000_f1.jpg"]
    assert result.cast[1].pictures == ["p001_f0.jpg"]


def test_records_a_failed_call_and_still_writes_assets(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)

    result = assets("demo", llm=BrokenLLM(), root=tmp_path)

    assert "endpoint down" in result.error
    assert result.cast == []
    assert (tmp_path / "demo" / "assets.json").is_file()


def test_reports_an_empty_cast(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)
    llm = FakeLLM({"cast": []})

    result = assets("demo", llm=llm, root=tmp_path)

    assert result.cast == []
    assert result.error == "model returned no cast"


def test_writes_empty_assets_for_a_book_without_content(tmp_path):
    make_book(tmp_path, [{}])
    llm = FakeLLM(CAST)

    result = assets("demo", llm=llm, root=tmp_path)

    assert llm.calls == 0
    assert result.cast == []
    assert result.locations == []
    assert result.error == ""


def test_reuses_the_cached_answer(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)
    llm = FakeLLM(CAST)
    cache_dir = tmp_path / "cache"

    first = assets("demo", llm=llm, root=tmp_path, cache=Cache(cache_dir))
    second = assets("demo", llm=llm, root=tmp_path, cache=Cache(cache_dir))

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
    result = assets("demo", llm=other, root=tmp_path, cache=Cache(cache_dir))

    assert first.calls == 1
    assert other.calls == 1
    assert result.model == "other-model"


def test_joins_the_two_errors(tmp_path):
    pages = [
        {
            "panels": [{"box": [0, 0, 800, 800], "description": "客厅"}],
            "figures": [figure([0, 0, 300, 700])],
        }
    ]
    make_book(tmp_path, pages)

    result = assets("demo", llm=BrokenLLM(), root=tmp_path)

    assert result.error.count("endpoint down") == 2
    assert "；" in result.error


def test_keeps_the_cast_when_only_the_place_call_fails(tmp_path):
    pages = [
        {
            "panels": [{"box": [0, 0, 800, 800], "description": "客厅"}],
            "figures": [figure([0, 0, 300, 700])],
        }
    ]
    make_book(tmp_path, pages)

    result = assets("demo", llm=PlacesBrokenLLM(CAST), root=tmp_path)

    assert [member.name for member in result.cast] == ["小满"]
    assert result.locations == []
    assert result.error == "locations down"


def test_records_a_reply_that_is_not_json(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)

    result = assets("demo", llm=RawLLM("抱歉，我看不清。"), root=tmp_path)

    assert result.cast == []
    assert "no JSON object found" in result.error


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

    result = assets("demo", llm=FakeLLM({}, reply), root=tmp_path)

    places = [(item.panel, item.location) for item in result.panel_locations]
    assert places == [(0, "l1"), (1, ""), (2, "")]
    assert result.locations[0].master == ""
    assert result.style == "水彩"


def test_leaves_a_crop_of_an_unknown_character_unowned(tmp_path):
    pages = [{"figures": [figure([0, 0, 300, 700])]}]
    make_book(tmp_path, pages)
    reply = {
        "cast": [{"key": "A", "name": "小满", "look": "红衣"}],
        "figure_cast": [{"file": "p000_f0.jpg", "key": "没这个标签"}],
    }

    result = assets("demo", llm=FakeLLM(reply), root=tmp_path)

    assert result.figure_cast[0].cast == ""
    assert result.cast[0].pictures == []
    assert result.unpictured == result.cast


def test_reports_an_empty_place_list(tmp_path):
    pages = [{"panels": [{"box": [0, 0, 800, 800], "description": "客厅"}]}]
    make_book(tmp_path, pages)

    result = assets("demo", llm=FakeLLM({}, {"style": "水彩"}), root=tmp_path)

    assert result.locations == []
    assert result.error == "model returned no location"


def test_reports_an_empty_style(tmp_path):
    pages = [{"panels": [{"box": [0, 0, 800, 800], "description": "客厅"}]}]
    make_book(tmp_path, pages)
    reply = {
        "locations": [{"key": "L1", "name": "客厅", "light": "白天"}],
        "panel_locations": [{"page": "p000.jpg", "panel": 0, "key": "L1"}],
    }

    result = assets("demo", llm=FakeLLM({}, reply), root=tmp_path)

    assert result.locations[0].id == "l1"
    assert result.error == "model returned no style"


def test_keeps_the_cast_error_when_the_places_also_fail(tmp_path):
    pages = [
        {
            "panels": [{"box": [0, 0, 800, 800], "description": "客厅"}],
            "figures": [figure([0, 0, 300, 700])],
        }
    ]
    make_book(tmp_path, pages)

    result = assets("demo", llm=FakeLLM({"cast": []}, {}), root=tmp_path)

    assert result.error == (
        "model returned no cast；model returned no location；"
        "model returned no style"
    )
