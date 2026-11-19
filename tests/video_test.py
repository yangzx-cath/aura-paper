from pathlib import Path

import pytest

from aura_paper.minimax import VideoTask
from aura_paper.prompts import shot_prompt
from aura_paper.screenplay import PageScene
from aura_paper.story import Story
from aura_paper.understand import BookContent, PageContent
from aura_paper.video import clip_path, generate_clip


class FakeMiniMax:
    model = "fake-model"

    def __init__(self):
        self.request = None
        self.downloaded = None

    def create_task(self, request):
        self.request = request
        return VideoTask("task-1", status="queued")

    def wait_task(self, task_id):
        return VideoTask(
            task_id,
            status="succeeded",
            video_url="https://example/video.mp4",
            duration=self.request.duration,
            resolution=self.request.resolution,
        )

    def download(self, url, path):
        self.downloaded = (url, str(path))
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"video")
        return target


def make_content(root: Path) -> tuple[BookContent, PageContent]:
    (root / "page_2.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    page = PageContent(
        index=1,
        filename="page_2.png",
        description="一只蓝色机器人捧着钱。",
        mood="期待",
    )
    content = BookContent(
        id="demo",
        source=str(root),
        pages=[page],
    )
    return content, page


def make_story() -> Story:
    return Story(
        id="demo",
        characters=["Kuan", "我"],
        setting="电影院",
        style="手绘",
        summary="Kuan 和我去看电影。",
    )


def test_shot_prompt_uses_the_scene_beat():
    page = PageContent(index=1, filename="page_2.png", description="画面")
    prompt = shot_prompt(page, make_story(), beat="我伸出手，把硬币托稳。")

    assert "我伸出手，把硬币托稳。" in prompt
    assert "（按画面自然动作）" not in prompt


def test_generate_clip_uses_scene_duration_and_beat(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=1, beat="我伸出手，把硬币托稳。", duration=9)
    client = FakeMiniMax()

    clip = generate_clip(
        content, page, make_story(), client, scene=scene, root=tmp_path
    )

    assert clip.error == ""
    assert clip.duration == 9
    assert clip.task_id == "task-1"
    assert client.request.duration == 9
    assert client.request.first_frame is None
    assert client.request.reference_images == [tmp_path / "page_2.png"]
    assert scene.beat in client.request.prompt
    assert clip_path("demo", 1, tmp_path).read_bytes() == b"video"


def test_explicit_duration_overrides_the_scene(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=1, beat="动作", duration=9)
    client = FakeMiniMax()

    generate_clip(
        content,
        page,
        make_story(),
        client,
        scene=scene,
        duration=6,
        root=tmp_path,
    )

    assert client.request.duration == 6


def test_generate_clip_rejects_a_mismatched_scene(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=2, beat="动作")

    with pytest.raises(ValueError, match="does not match"):
        generate_clip(content, page, make_story(), FakeMiniMax(), scene=scene)


def test_generate_clip_stops_on_a_scene_error(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=1, beat="动作", error="no beat")
    client = FakeMiniMax()

    clip = generate_clip(
        content, page, make_story(), client, scene=scene, root=tmp_path
    )

    assert clip.error == "no beat"
    assert client.request is None
    assert not clip_path("demo", 1, tmp_path).exists()
