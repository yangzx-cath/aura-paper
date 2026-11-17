import json

from aura_paper.cache import Cache
from aura_paper.llm import LLMClient
from aura_paper.screenplay import Line, PageScene, Screenplay, build_screenplay
from aura_paper.story import Story
from aura_paper.understand import BookContent, PageContent


class FakeClient(LLMClient):
    def __init__(self, reply=""):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.reply = reply
        self.prompts = []

    def chat(self, prompt, *, image_path=None, json_mode=True):
        self.prompts.append(prompt)
        return self.reply


def make_story():
    return Story(
        id="demo",
        characters=["Kuan"],
        setting="电影院",
        style="纸纹拼贴",
        summary="兄弟俩去看电影。",
    )


def make_content(count=3, roles=None):
    pages = []
    for index in range(count):
        pages.append(
            PageContent(
                index=index,
                filename=f"{index:02d}.jpg",
                page_text=f"第 {index + 1} 页原文",
                description=f"第 {index + 1} 页画面",
            )
        )
    for index, role in (roles or {}).items():
        pages[index].role = role
    return BookContent(id="demo", title="示例", source="/src", pages=pages)


def make_reply(**overrides):
    data = {
        "beat": "这一页推进了什么。",
        "lines": [
            {"kind": "narration", "speaker": "", "text": "旁白一句话。"}
        ],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def test_unknown_line_kind_falls_back_to_narration():
    line = Line.from_dict({"kind": "narrative", "text": "春天来了。"})
    assert line.kind == "narration"


def test_lines_that_are_not_a_list_become_empty():
    scene = PageScene.from_dict({"index": 1, "lines": "小鸡球球：你好"})
    assert scene.lines == []


def test_non_object_lines_are_skipped():
    scene = PageScene.from_dict(
        {"index": 1, "lines": [None, {"text": "你好"}]}
    )
    assert [line.text for line in scene.lines] == ["你好"]


def test_missing_duration_uses_the_default():
    scene = PageScene.from_dict({"index": 1})
    assert scene.duration == 6


def test_pages_that_are_not_a_list_become_empty():
    screenplay = Screenplay.from_dict({"id": "demo", "pages": {"0": {}}})
    assert screenplay.pages == []


def test_skips_pages_that_are_not_story():
    content = make_content(roles={0: "cover", 2: "end"})

    screenplay = build_screenplay(
        content, make_story(), FakeClient(make_reply())
    )

    assert [scene.index for scene in screenplay.pages] == [1]


def test_gives_each_page_the_text_of_the_one_before():
    client = FakeClient(make_reply())

    build_screenplay(make_content(), make_story(), client)

    assert "第 1 页原文" in client.prompts[1]
    assert "第 3 页原文" not in client.prompts[1]
    assert "（这是第一页）" in client.prompts[0]


def test_missing_lines_are_an_error():
    client = FakeClient(json.dumps({"beat": "有情节"}, ensure_ascii=False))

    screenplay = build_screenplay(make_content(1), make_story(), client)

    assert screenplay.pages[0].error == "model returned no lines"


def test_a_page_that_does_not_fit_one_clip_is_an_error():
    text = "这一页的台词很长很长。" * 8
    reply = make_reply(lines=[{"kind": "narration", "text": text}])
    client = FakeClient(reply)

    screenplay = build_screenplay(make_content(1), make_story(), client)

    assert "over the 15s limit" in screenplay.pages[0].error


def test_a_failed_scene_is_not_cached(tmp_path):
    cache = Cache(tmp_path / "cache")
    client = FakeClient(json.dumps({"beat": "有情节"}, ensure_ascii=False))

    build_screenplay(make_content(1), make_story(), client, cache=cache)

    assert not (tmp_path / "cache" / "screenplay").exists()


def test_duration_is_computed_again_on_a_cache_hit(tmp_path):
    cache = Cache(tmp_path / "cache")
    content = make_content(1)
    text = "这是一句很长的旁白，念出来要好几秒钟才不会显得急促。"
    reply = make_reply(lines=[{"kind": "narration", "text": text}])
    first = build_screenplay(
        content, make_story(), FakeClient(reply), cache=cache
    )

    second = FakeClient("")
    screenplay = build_screenplay(content, make_story(), second, cache=cache)

    assert second.prompts == []
    assert first.pages[0].duration > 6
    assert screenplay.pages[0].duration == first.pages[0].duration
