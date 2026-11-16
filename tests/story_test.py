import json
from pathlib import Path

from aura_paper.cache import Cache
from aura_paper.llm import LLMClient, LLMError
from aura_paper.prompts import story_prompt
from aura_paper.story import Story, build_story, save_story
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
    pages = []
    for index in range(count):
        pages.append(
            PageContent(
                index=index,
                filename=f"{index:02d}.jpg",
                description=f"第 {index + 1} 页的画面",
            )
        )
    return BookContent(id="demo", title="示例", source="/src", pages=pages)


def make_reply(count=3, **overrides):
    data = {
        "characters": ["小鸡球球", "向日葵"],
        "setting": "春天的小山坡",
        "style": "手绘水彩，柔和明亮",
        "summary": "小鸡球球种下向日葵，并一直守护它长大。",
        "beats": [f"第 {i + 1} 页推进了什么" for i in range(count)],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def test_builds_story_fields():
    story = build_story(make_content(), FakeClient(make_reply()))

    assert story.characters == ["小鸡球球", "向日葵"]
    assert story.setting == "春天的小山坡"
    assert story.style.startswith("手绘水彩")
    assert story.summary.startswith("小鸡球球")
    assert len(story.beats) == 3
    assert story.error == ""


def test_sends_the_story_prompt():
    client = FakeClient(make_reply())
    content = make_content()

    build_story(content, client)

    assert client.prompts == [story_prompt(content)]


def test_beat_count_mismatch_is_an_error():
    reply = make_reply(count=2)

    story = build_story(make_content(count=3), FakeClient(reply))

    assert story.error == "expected 3 beats, got 2"


def test_beats_given_as_text_is_an_error():
    reply = make_reply(beats="共三页的情节")

    story = build_story(make_content(), FakeClient(reply))

    assert "expected 3 beats" in story.error


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
    assert story.beats == []


def test_cache_reuses_the_story(tmp_path):
    cache = Cache(tmp_path / "cache")
    content = make_content()
    build_story(content, FakeClient(make_reply()), cache=cache)

    second = FakeClient("")
    story = build_story(content, second, cache=cache)

    assert second.prompts == []
    assert len(story.beats) == 3
    assert cache.stats() == {"hit": 1, "miss": 1}


def test_failed_story_is_not_cached(tmp_path):
    cache = Cache(tmp_path / "cache")
    reply = make_reply(count=1)

    build_story(make_content(count=3), FakeClient(reply), cache=cache)

    assert not (tmp_path / "cache" / "story").exists()


def test_save_story_writes_story_json(tmp_path):
    story = build_story(make_content(), FakeClient(make_reply()))

    path = save_story(story, "demo", tmp_path)

    assert path == tmp_path / "demo" / "story.json"
    assert path.is_file()


def test_save_story_writes_the_story_fields(tmp_path):
    story = build_story(make_content(), FakeClient(make_reply()))

    path = save_story(story, "demo", tmp_path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["characters"] == ["小鸡球球", "向日葵"]
    assert data["summary"].startswith("小鸡球球")
    assert len(data["beats"]) == 3


def test_story_dict_round_trip():
    story = Story(
        characters=["小鸡球球"],
        setting="春天的小山坡",
        style="手绘水彩",
        summary="种下向日葵并守护它长大。",
        beats=["第一页", "第二页"],
        model="m",
    )

    assert Story.from_dict(story.to_dict()) == story
