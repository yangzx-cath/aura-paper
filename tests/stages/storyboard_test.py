import json

from PIL import Image

from aura_paper.clients.llm import LLMClient, LLMError
from aura_paper.schema.cast import BookCast
from aura_paper.schema.content import BookContent
from aura_paper.schema.location import BookLocations
from aura_paper.stages.storyboard import storyboard
from aura_paper.store.cache import Cache
from aura_paper.store.output import write_json

# A box that covers most of the page, so the panel shows a whole scene.
FULL_BOX = [0, 0, 800, 800]

# A small box, so the panel has no background of its own.
BLANK_BOX = [0, 0, 300, 300]


# Reply with a fixed plan, whatever was asked.
class FakeLLM(LLMClient):
    def __init__(self, reply, model="fake-model"):
        super().__init__("http://example/v1", "test-key", model)
        self.reply = reply
        self.calls = 0

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        self.calls += 1
        return json.dumps(self.reply)


# Answer every call with the same text, whatever was asked.
class RawLLM(LLMClient):
    def __init__(self, reply):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.reply = reply

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        return self.reply


# Fail every call, the way an unreachable endpoint does.
class BrokenLLM(LLMClient):
    def __init__(self):
        super().__init__("http://example/v1", "test-key", "fake-model")

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        raise LLMError("endpoint down")


# Describe one panel with a box, its text and what it draws.
def panel(box, text="三块、", description="搭积木"):
    return {"box": box, "text": text, "description": description}


# Write the three artifacts the stage reads, plus the images they name.
def make_book(root, pages, members=None):
    folder = root / "demo"
    for name in ("pages", "panels", "figures"):
        (folder / name).mkdir(parents=True, exist_ok=True)

    records = []
    for index, page in enumerate(pages):
        name = f"p{index:03d}.jpg"
        Image.new("RGB", (100, 120), "white").save(folder / "pages" / name)
        records.append(
            {
                "index": index,
                "filename": name,
                "width": 100,
                "height": 120,
                "panels": page.get("panels", []),
            }
        )
        for number in range(len(page.get("panels", []))):
            crop = folder / "panels" / f"p{index:03d}_{number}.jpg"
            Image.new("RGB", (100, 120), "white").save(crop)

    content = BookContent.from_dict({"id": "demo", "pages": records})
    write_json("demo", "understand", content.to_dict(), root)

    cast = BookCast.from_dict(
        {
            "id": "demo",
            "cast": members
            or [
                {
                    "id": "c1",
                    "name": "小满",
                    "look": "红衣",
                    "pictures": ["p000_f0.jpg"],
                },
            ],
        }
    )
    write_json("demo", "cast", cast.to_dict(), root)
    for member in cast.cast:
        for name in member.pictures:
            Image.new("RGB", (40, 60), "white").save(folder / "figures" / name)

    places = BookLocations.from_dict(
        {
            "id": "demo",
            "style": "水彩",
            "locations": [
                {
                    "id": "l1",
                    "name": "客厅",
                    "light": "白天",
                    "master": "p000_0.jpg",
                }
            ],
        }
    )
    write_json("demo", "locations", places.to_dict(), root)


# Reply with one plan and one narration rewrite.
class TwoLLM(LLMClient):
    def __init__(self, plan, spoken, model="fake-model"):
        super().__init__("http://example/v1", "test-key", model)
        self.plan = plan
        self.spoken = spoken
        self.calls = 0

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        self.calls += 1
        if "朗读编剧" in prompt:
            return json.dumps(self.spoken)
        return json.dumps(self.plan)


# Describe one shot as the model would write it.
def shot(scene, page, index, **extra):
    entry = {
        "scene": scene,
        "panels": [{"page": page, "panel": index}],
        "cast": ["c1"],
        "join": "硬切",
        "camera": "中景",
        "beats": ["搭积木"],
        "audio": [{"kind": "旁白", "text": "三块、", "cast": ""}],
        "continuity": "接上一镜",
    }
    entry.update(extra)
    return entry


def test_drops_a_sound_effect_the_review_cannot_explain(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX, text="吱呀——")]}])
    reply = {
        "scenes": [
            {
                "key": "A",
                "name": "跑开",
                "location": "l1",
                "pages": ["p000.jpg"],
            }
        ],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[{"kind": "音效", "text": "吱呀——", "cast": ""}],
            )
        ],
    }
    spoken = {
        "lines": [],
        "sounds": [{"shot": "j1", "index": 0, "keep": False}],
    }

    _, shot_book = storyboard("demo", llm=TwoLLM(reply, spoken), root=tmp_path)

    assert shot_book.shots[0].audio == []
    assert "音效" in shot_book.error


def test_numbers_scenes_and_shots(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [
            {
                "key": "A",
                "name": "搭积木",
                "location": "l1",
                "pages": ["p000.jpg", "p999.jpg"],
            }
        ],
        "shots": [shot("A", "p000.jpg", 0, cast=["c1", "c9"])],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    assert [scene.id for scene in scene_book.scenes] == ["s1"]
    # A page outside the book cannot belong to a scene.
    assert scene_book.scenes[0].pages == ["p000.jpg"]
    assert [item.id for item in shot_book.shots] == ["j1"]
    assert shot_book.shots[0].scene == "s1"
    # A character outside the cast cannot appear in a shot.
    assert shot_book.shots[0].cast == ["c1"]
    assert shot_book.error == ""


def test_cuts_a_shot_that_spans_pages_between_the_pages(tmp_path):
    pages = [
        {
            "panels": [
                panel(BLANK_BOX, text=f"第{number}块、") for number in range(3)
            ]
        },
        {
            "panels": [
                panel(BLANK_BOX, text=f"第{number}块、")
                for number in range(3, 6)
            ]
        },
    ]
    make_book(tmp_path, pages)
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            {
                "scene": "A",
                "panels": [
                    {"page": "p000.jpg", "panel": number}
                    for number in range(3)
                ]
                + [
                    {"page": "p001.jpg", "panel": number}
                    for number in range(3)
                ],
                "cast": ["c1"],
                "camera": "中景",
                "beats": [f"第{number}步" for number in range(6)],
                "audio": [
                    {"kind": "旁白", "text": f"第{number}块、", "cast": ""}
                    for number in (0, 4)
                ],
            }
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    # Six panels over two pages do not fit one clip, and the cut lands
    # between the pages, so each clip covers one whole page.
    assert [len(item.panels) for item in shot_book.shots] == [3, 3]
    assert [item.page for item in shot_book.shots[1].panels] == [
        "p001.jpg"
    ] * 3
    # Each line of sound travels with the panel it is printed on.
    voices = [[line.text for line in item.audio] for item in shot_book.shots]
    assert voices == [["第0块、"], ["第4块、"]]
    # The beats follow their own panels too.
    assert shot_book.shots[1].beats == ["第3步", "第4步", "第5步"]


def test_keeps_a_whole_page_that_holds_more_panels_than_a_clip(tmp_path):
    pages = [
        {
            "panels": [
                panel(BLANK_BOX, text=f"第{number}块、") for number in range(5)
            ]
        }
    ]
    make_book(tmp_path, pages)
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            {
                "scene": "A",
                "panels": [
                    {"page": "p000.jpg", "panel": number}
                    for number in range(5)
                ],
                "cast": ["c1"],
                "camera": "中景",
                "beats": [f"第{number}步" for number in range(5)],
                "audio": [{"kind": "旁白", "text": "第0块、", "cast": ""}],
            }
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    # The page stays in one piece, however many panels it holds.
    assert [len(item.panels) for item in shot_book.shots] == [5]
    assert shot_book.error == ""


def test_drops_a_shot_without_a_panel(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [shot("A", "p000.jpg", 0), shot("A", "p000.jpg", 9)],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    assert [item.id for item in shot_book.shots] == ["j1"]
    assert "第 9 块不存在" in shot_book.error


def test_fills_the_join_from_the_scene_change(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [
            {"key": "A", "name": "搭积木", "location": "l1"},
            {"key": "B", "name": "草地", "location": "l1"},
        ],
        "shots": [
            shot("A", "p000.jpg", 0, join=""),
            shot("B", "p000.jpg", 0, join=""),
            shot("B", "p000.jpg", 0, join=""),
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    # The first shot fades in, a scene change dissolves, staying cuts.
    assert [item.join for item in shot_book.shots] == ["叠化", "叠化", "硬切"]


def test_records_a_sound_kind_it_does_not_know(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[{"kind": "独白", "text": "三块、", "cast": ""}],
            )
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    # The text is kept, so nothing is lost, and the kind is left empty.
    assert shot_book.shots[0].audio[0].text == "三块、"
    assert shot_book.shots[0].audio[0].kind == ""
    assert "1 条声音的类型不认识" in shot_book.error


def test_keeps_one_voice_when_two_people_say_a_line(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[{"kind": "对白", "text": "三块、", "cast": "c1,c2"}],
            )
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    assert shot_book.shots[0].audio[0].cast == "c1"


def test_matches_a_line_back_to_the_printed_text(tmp_path):
    printed = "“我们一起搭城堡。”"
    make_book(tmp_path, [{"panels": [panel(FULL_BOX, text=printed)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[
                    {
                        "kind": "对白",
                        "text": "“我们 一起搭城堡。”",
                        "cast": "c1",
                    }
                ],
            )
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    # The space the model added is dropped, so the voice reads the page.
    assert shot_book.shots[0].audio[0].text == printed
    assert shot_book.error == ""


def test_reports_a_line_the_page_does_not_hold(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX, text="三块、")]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[{"kind": "旁白", "text": "十块、", "cast": ""}],
            )
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    assert shot_book.shots[0].audio[0].text == "十块、"
    assert "1 行文字在原文里找不到" in shot_book.error


def test_reports_a_dialogue_without_a_voice(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[{"kind": "对白", "text": "三块、", "cast": ""}],
            )
        ],
    }

    scene_book, shot_book = storyboard(
        "demo",
        llm=FakeLLM(reply),
        root=tmp_path,
    )

    assert "1 句对白没有说话人" in shot_book.error


def test_reuses_the_cached_plan(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [shot("A", "p000.jpg", 0)],
    }
    llm = FakeLLM(reply)
    cache_dir = tmp_path / "cache"

    first = storyboard("demo", llm=llm, root=tmp_path, cache=Cache(cache_dir))
    second = storyboard("demo", llm=llm, root=tmp_path, cache=Cache(cache_dir))

    assert llm.calls == 2
    assert [item.id for item in second[1].shots] == ["j1"]
    assert second[1].shots == first[1].shots
    assert (cache_dir / "storyboard" / "demo").is_dir()


def test_writes_the_file_when_the_call_fails(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])

    scene_book, shot_book = storyboard("demo", llm=BrokenLLM(), root=tmp_path)

    assert shot_book.shots == []
    assert shot_book.error == "endpoint down"
    assert scene_book.error == "endpoint down"
    assert (tmp_path / "demo" / "scenes.json").is_file()
    assert (tmp_path / "demo" / "shots.json").is_file()


def test_writes_the_file_when_the_reply_is_not_json(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])

    scene_book, shot_book = storyboard(
        "demo",
        llm=RawLLM("抱歉，我看不清。"),
        root=tmp_path,
    )

    assert "no JSON object found" in shot_book.error
    assert (tmp_path / "demo" / "shots.json").is_file()


def test_reads_the_thumbnail_images_it_sends(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX), panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [shot("A", "p000.jpg", 0)],
    }

    storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    thumbs = sorted(
        name.name for name in (tmp_path / "demo" / "thumbs").iterdir()
    )
    # Two panels first, then the one character reference.
    assert thumbs == ["p000_0.jpg", "p000_1.jpg", "p000_f0.jpg"]


def test_joins_neighbouring_lines_of_one_speaker(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[
                    {"kind": "旁白", "text": "三块、", "cast": ""},
                    {"kind": "旁白", "text": "四块、", "cast": ""},
                    {"kind": "对白", "text": "还没倒！", "cast": "c1"},
                    {"kind": "音效", "text": "阿嚏！", "cast": ""},
                    {"kind": "旁白", "text": "五块、", "cast": ""},
                ],
            )
        ],
    }

    _, shot_book = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    kept = [(line.kind, line.text) for line in shot_book.shots[0].audio]
    # The two counting lines join, the sound breaks the run.
    assert kept == [
        ("旁白", "三块、四块、"),
        ("对白", "还没倒！"),
        ("音效", "阿嚏！"),
        ("旁白", "五块、"),
    ]


def test_rewrites_the_narration_and_cleans_the_dialogue(tmp_path):
    printed = "花花放上小木门。“还没倒！”"
    make_book(tmp_path, [{"panels": [panel(FULL_BOX, text=printed)]}])
    plan = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[
                    {"kind": "旁白", "text": "花花放上小木门。", "cast": ""},
                    {"kind": "对白", "text": "“还没倒！”", "cast": "c1"},
                ],
            )
        ],
    }
    spoken = {
        "lines": [{"shot": "j1", "index": 0, "spoken": "花花把小木门放上去。"}]
    }

    _, shot_book = storyboard("demo", llm=TwoLLM(plan, spoken), root=tmp_path)

    lines = shot_book.shots[0].audio
    # The page keeps its own words, the voice reads the rewrite.
    assert lines[0].text == "花花放上小木门。"
    assert lines[0].spoken == "花花把小木门放上去。"
    # Dialogue is not rewritten, only stripped of printing quotes.
    assert lines[1].text == "“还没倒！”"
    assert lines[1].spoken == "还没倒！"
    assert shot_book.error == ""


def test_falls_back_when_a_rewrite_changes_a_number(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    plan = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot(
                "A",
                "p000.jpg",
                0,
                audio=[
                    {"kind": "旁白", "text": "三块、", "cast": ""},
                ],
            )
        ],
    }
    spoken = {"lines": [{"shot": "j1", "index": 0, "spoken": "很多块积木。"}]}

    _, shot_book = storyboard("demo", llm=TwoLLM(plan, spoken), root=tmp_path)

    line = shot_book.shots[0].audio[0]
    assert line.spoken == "三块、"
    assert "改写不合格" in shot_book.error
