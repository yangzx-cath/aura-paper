from aura_paper.screenplay import Line, PageScene, Screenplay


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
