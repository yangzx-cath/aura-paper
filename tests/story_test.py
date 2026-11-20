import json
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.llm import LLMClient, LLMError
from aura_paper.prompts import story_prompt
from aura_paper.story import Cast, Resolution, Story, build_story, save_story
from aura_paper.understand import BookContent, PageContent


class FakeClient(LLMClient):
    def __init__(self, reply="", error=None):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.reply = reply
        self.error = error
        self.prompts = []

    def chat(
        self,
        prompt: str,
        *,
        image_path: Path | None = None,
        json_mode: bool = True,
    ) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def make_content(count=3):
    pages = [PageContent(index=0, filename="00.jpg", page_text="封面")]
    for index in range(1, count + 1):
        pages.append(
            PageContent(
                index=index,
                filename=f"{index:02d}.jpg",
                description=f"第 {index + 1} 页的画面",
            )
        )
    return BookContent(id="demo", source="/src", pages=pages)


def make_reply(**overrides):
    data = {
        "characters": ["小鸡球球", "向日葵"],
        "cast": [
            {"name": "小鸡球球", "look": "圆滚滚的黄色小鸡"},
            {"name": "向日葵", "look": "比小鸡还高的一朵花"},
        ],
        "setting": "春天的小山坡",
        "style": "手绘水彩，柔和明亮",
        "summary": "小鸡球球种下向日葵，并一直守护它长大。",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def test_builds_story_fields():
    story = build_story(make_content(), FakeClient(make_reply()))

    assert story.characters == ["小鸡球球", "向日葵"]
    assert story.cast[0] == Cast("小鸡球球", "圆滚滚的黄色小鸡")
    assert story.setting == "春天的小山坡"
    assert story.style.startswith("手绘水彩")
    assert story.summary.startswith("小鸡球球")
    assert story.resolved == []
    assert story.unresolved == []
    assert story.error == ""


def test_reads_resolved_and_unresolved_items():
    reply = make_reply(
        resolved=[
            {
                "index": 18,
                "issue": "手的主人",
                "answer": "我",
                "evidence": "第18页文字提到 Kuan and I",
            }
        ],
        unresolved=[
            {
                "index": 26,
                "issue": "画面中的女孩是谁",
                "reason": "全书没有直接称呼",
            }
        ],
    )

    story = build_story(make_content(), FakeClient(reply))

    assert story.resolved == [
        Resolution(
            18,
            "手的主人",
            "我",
            "第18页文字提到 Kuan and I",
        )
    ]
    assert story.unresolved == [
        Resolution(26, "画面中的女孩是谁", reason="全书没有直接称呼")
    ]


def test_resolution_lists_ignore_malformed_items():
    reply = make_reply(
        resolved="不是数组",
        unresolved=[None, {}, {"index": 1, "issue": "说话人"}],
    )

    story = build_story(make_content(), FakeClient(reply))

    assert story.resolved == []
    assert story.unresolved == [Resolution(1, "说话人")]


def test_sends_the_story_prompt():
    client = FakeClient(make_reply())
    content = make_content()

    build_story(content, client)

    assert client.prompts == [story_prompt(content)]


def test_leaves_cover_pages_out_of_the_prompt():
    content = make_content()
    # Page 0 is the cover, so its printed text never reaches the story.
    content.pages[0].page_text = "湖北长江出版集团"

    prompt = story_prompt(content)

    assert "湖北长江出版集团" not in prompt
    assert "共 3 页" in prompt


def test_missing_summary_is_an_error():
    reply = make_reply(summary="")

    story = build_story(make_content(), FakeClient(reply))

    assert story.error == "model returned no summary"


def test_bad_json_is_recorded():
    story = build_story(make_content(), FakeClient("抱歉，我做不到"))

    assert "no JSON object" in story.error


def test_llm_error_is_recorded():
    client = FakeClient(error=LLMError("boom"))

    story = build_story(make_content(), client)

    assert story.error == "boom"


def test_cache_reuses_the_story(tmp_path):
    cache = Cache(tmp_path / "cache")
    content = make_content()
    build_story(content, FakeClient(make_reply()), cache=cache)

    second = FakeClient("")
    story = build_story(content, second, cache=cache)

    assert second.prompts == []
    assert story.summary.startswith("小鸡球球")
    assert cache.stats() == {"hit": 1, "miss": 1}


def test_failed_story_is_not_cached(tmp_path):
    cache = Cache(tmp_path / "cache")
    reply = make_reply(summary="")

    build_story(make_content(), FakeClient(reply), cache=cache)

    assert not (tmp_path / "cache" / "story").exists()


def test_save_story_writes_story_json(tmp_path):
    story = build_story(make_content(), FakeClient(make_reply()))

    path = save_story(story, tmp_path)

    assert path == tmp_path / "demo" / "story.json"
    assert path.is_file()


def test_cast_entries_without_a_name_are_skipped():
    reply = make_reply(
        cast=[
            None,
            {"look": "没有名字"},
            {"name": "小鸡球球", "look": "圆滚滚的黄色小鸡"},
        ]
    )

    story = build_story(make_content(), FakeClient(reply))

    assert [member.name for member in story.cast] == ["小鸡球球"]


def test_save_story_writes_the_story_fields(tmp_path):
    story = build_story(make_content(), FakeClient(make_reply()))

    path = save_story(story, tmp_path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "demo"
    assert data["characters"] == ["小鸡球球", "向日葵"]
    assert data["cast"][0]["look"] == "圆滚滚的黄色小鸡"
    assert data["summary"].startswith("小鸡球球")
    assert data["resolved"] == []
    assert data["unresolved"] == []


def test_story_dict_round_trip():
    story = Story(
        id="demo",
        characters=["小鸡球球"],
        cast=[Cast("小鸡球球", "圆滚滚的黄色小鸡")],
        setting="春天的小山坡",
        style="手绘水彩",
        summary="种下向日葵并守护它长大。",
        resolved=[Resolution(18, "手的主人", "我", "文字依据")],
        unresolved=[Resolution(26, "女孩身份", reason="缺少文字依据")],
        model="m",
    )

    assert Story.from_dict(story.to_dict()) == story
