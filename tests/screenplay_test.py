import json

from aura_paper.cache import Cache
from aura_paper.llm import LLMClient
from aura_paper.screenplay import Line, PageScene, Screenplay, build_screenplay
from aura_paper.story import Cast, Resolution, Story
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
        cast=[Cast("Kuan", "圆滚滚的蓝色机器人")],
        setting="电影院",
        style="纸纹拼贴",
        summary="兄弟俩去看电影。",
    )


def make_content(count=3):
    pages = [PageContent(index=0, filename="00.jpg", page_text="封面")]
    for index in range(1, count + 1):
        pages.append(
            PageContent(
                index=index,
                filename=f"{index:02d}.jpg",
                page_text=f"第 {index + 1} 页原文",
                description=f"第 {index + 1} 页画面",
            )
        )
    return BookContent(id="demo", source="/src", pages=pages)


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


def test_skips_the_cover_page():
    content = make_content()

    screenplay = build_screenplay(
        content, make_story(), FakeClient(make_reply())
    )

    assert [scene.index for scene in screenplay.pages] == [1, 2, 3]


def test_gives_each_page_the_text_of_the_one_before():
    client = FakeClient(make_reply())

    build_screenplay(make_content(), make_story(), client)

    # The first story page has no story page before it, so it starts the chain.
    assert "（这是第一页）" in client.prompts[0]
    assert "第 2 页原文" in client.prompts[1]
    assert "第 1 页原文" not in client.prompts[1]


def test_uses_story_page_index():
    client = FakeClient(make_reply())

    build_screenplay(make_content(1), make_story(), client)

    assert "故事页：第 1 页" in client.prompts[0]


def test_includes_page_scoped_resolution_context():
    content = make_content(2)
    content.pages[1].uncertain = ["手的主人"]
    story = make_story()
    story.resolved = [
        Resolution(1, "手的主人", "我", "第18页文字依据"),
        Resolution(2, "说话人", "Kuan", "第19页文字依据"),
    ]
    story.unresolved = [
        Resolution(1, "女孩身份", reason="缺少文字依据"),
    ]
    client = FakeClient(make_reply())

    build_screenplay(content, story, client)

    first = client.prompts[0]
    assert "uncertain：\n- 手的主人" in first
    assert "结论：我" in first
    assert "依据：第18页文字依据" in first
    assert "原因：缺少文字依据" in first
    assert "结论：Kuan" not in first

    second = client.prompts[1]
    assert "结论：Kuan" in second
    assert "结论：我" not in second


def test_tells_the_model_how_each_character_looks():
    client = FakeClient(make_reply())

    build_screenplay(make_content(1), make_story(), client)

    assert "Kuan（圆滚滚的蓝色机器人）" in client.prompts[0]


def test_tells_the_model_which_language_to_speak():
    client = FakeClient(make_reply())

    build_screenplay(make_content(1), make_story(), client)

    assert "- 语言：中文" in client.prompts[0]


def test_a_silent_page_is_not_an_error():
    client = FakeClient(json.dumps({"beat": "有情节"}, ensure_ascii=False))

    screenplay = build_screenplay(make_content(1), make_story(), client)

    assert screenplay.pages[0].error == ""
    assert screenplay.pages[0].duration == 4


def test_missing_beat_is_an_error():
    reply = make_reply(beat="")

    screenplay = build_screenplay(
        make_content(1), make_story(), FakeClient(reply)
    )

    assert screenplay.pages[0].error == "model returned no beat"


def test_a_page_that_does_not_fit_one_clip_is_an_error():
    text = "这一页的台词很长很长。" * 8
    reply = make_reply(lines=[{"kind": "narration", "text": text}])
    client = FakeClient(reply)

    screenplay = build_screenplay(make_content(1), make_story(), client)

    assert "over the 15s limit" in screenplay.pages[0].error


def test_a_failed_scene_is_not_cached(tmp_path):
    cache = Cache(tmp_path / "cache")
    client = FakeClient(make_reply(beat=""))

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
