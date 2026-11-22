import json

from PIL import Image

from aura_paper.cache import Cache
from aura_paper.clients.llm import LLMClient, LLMError
from aura_paper.output import write_json
from aura_paper.schema.cast import BookCast
from aura_paper.schema.content import BookContent
from aura_paper.schema.location import BookLocations
from aura_paper.stages.storyboard import storyboard

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
def make_book(root, pages):
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
            "cast": [
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
    Image.new("RGB", (40, 60), "white").save(
        folder / "figures" / "p000_f0.jpg"
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
                    "master": "p000_0.jpg",
                }
            ],
        }
    )
    write_json("demo", "locations", places.to_dict(), root)


# Describe one shot as the model would write it.
def shot(scene, page, index, **extra):
    entry = {
        "scene": scene,
        "page": page,
        "panel": index,
        "cast": ["c1"],
        "mode": "首帧",
        "join": "硬切",
        "camera": "中景",
        "beats": ["搭积木"],
        "audio": [{"kind": "旁白", "text": "三块、", "cast": ""}],
        "continuity": "接上一镜",
    }
    entry.update(extra)
    return entry


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

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    assert [scene.id for scene in result.scenes] == ["s1"]
    # A page outside the book cannot belong to a scene.
    assert result.scenes[0].pages == ["p000.jpg"]
    assert [item.id for item in result.shots] == ["j1"]
    assert result.shots[0].scene == "s1"
    # A character outside the cast cannot appear in a shot.
    assert result.shots[0].cast == ["c1"]
    assert result.error == ""


def test_forces_a_widened_shot_for_a_blank_panel(tmp_path):
    make_book(
        tmp_path,
        [{"panels": [panel(FULL_BOX), panel(BLANK_BOX)]}],
    )
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [
            shot("A", "p000.jpg", 0),
            shot("A", "p000.jpg", 1, mode="首帧"),
        ],
    }

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    assert [item.mode for item in result.shots] == ["首帧", "扩景"]


def test_drops_a_shot_without_a_panel(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])
    reply = {
        "scenes": [{"key": "A", "name": "搭积木", "location": "l1"}],
        "shots": [shot("A", "p000.jpg", 0), shot("A", "p000.jpg", 9)],
    }

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    assert [item.id for item in result.shots] == ["j1"]
    assert "第 9 块不存在" in result.error


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

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    # The first shot fades in, a scene change dissolves, staying cuts.
    assert [item.join for item in result.shots] == ["叠化", "叠化", "硬切"]


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

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    # The text is kept, so nothing is lost, and the kind is left empty.
    assert result.shots[0].audio[0].text == "三块、"
    assert result.shots[0].audio[0].kind == ""
    assert "1 条声音的类型不认识" in result.error


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

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    assert result.shots[0].audio[0].cast == "c1"


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

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    # The space the model added is dropped, so the voice reads the page.
    assert result.shots[0].audio[0].text == printed
    assert result.error == ""


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

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    assert result.shots[0].audio[0].text == "十块、"
    assert "1 行文字在原文里找不到" in result.error


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

    result = storyboard("demo", llm=FakeLLM(reply), root=tmp_path)

    assert "1 句对白没有说话人" in result.error


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

    assert llm.calls == 1
    assert [item.id for item in second.shots] == ["j1"]
    assert second.shots == first.shots
    assert (cache_dir / "storyboard" / "demo").is_dir()


def test_writes_the_file_when_the_call_fails(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])

    result = storyboard("demo", llm=BrokenLLM(), root=tmp_path)

    assert result.shots == []
    assert result.error == "endpoint down"
    assert (tmp_path / "demo" / "storyboard.json").is_file()


def test_writes_the_file_when_the_reply_is_not_json(tmp_path):
    make_book(tmp_path, [{"panels": [panel(FULL_BOX)]}])

    result = storyboard("demo", llm=RawLLM("抱歉，我看不清。"), root=tmp_path)

    assert "no JSON object found" in result.error
    assert (tmp_path / "demo" / "storyboard.json").is_file()


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
