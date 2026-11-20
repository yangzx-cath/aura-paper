from pathlib import Path

import pytest

from aura_paper.cache import Cache
from aura_paper.clips import VideoClip, build_clips, clip_path, generate_clip
from aura_paper.minimax import VideoTask
from aura_paper.prompts import clip_prompt
from aura_paper.screenplay import PageScene, Screenplay
from aura_paper.story import Story
from aura_paper.understand import BookContent, PageContent


class FakeMiniMax:
    model = "fake-model"

    def __init__(self):
        self.request = None
        self.requests = []
        self.downloaded = None

    def create_task(self, request):
        self.request = request
        self.requests.append(request)
        return VideoTask(f"task-{len(self.requests)}", status="queued")

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


class HalfFailingMiniMax(FakeMiniMax):
    def wait_task(self, task_id):
        if task_id == "task-2":
            return VideoTask(task_id, status="failed", error="boom")
        return super().wait_task(task_id)


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


def test_clip_prompt_uses_the_scene_beat():
    page = PageContent(index=1, filename="page_2.png", description="画面")
    prompt = clip_prompt(page, make_story(), beat="我伸出手，把硬币托稳。")

    assert "我伸出手，把硬币托稳。" in prompt
    assert "（按画面自然动作）" not in prompt


def test_the_camera_follows_the_page_shape():
    story = make_story()
    upright = PageContent(index=1, filename="01.png", description="画面")
    wide = PageContent(
        index=2, filename="02.png", kind="landscape", description="画面"
    )

    assert "[Push in]" in clip_prompt(upright, story)
    assert "从左到右缓慢平移" in clip_prompt(wide, story)
    assert "镜头保持稳定" not in clip_prompt(upright, story)


def test_generate_clip_uses_scene_duration_and_beat(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=1, beat="我伸出手，把硬币托稳。", duration=9)
    client = FakeMiniMax()

    clip = generate_clip(
        content, page, make_story(), scene, client, root=tmp_path
    )

    assert clip.error == ""
    assert clip.duration == 9
    assert clip.task_id == "task-1"
    assert client.request.duration == 9
    assert client.request.first_frame is None
    assert client.request.reference_images == [tmp_path / "page_2.png"]
    assert scene.beat in client.request.prompt
    assert clip_path("demo", "page_2.png", tmp_path).read_bytes() == b"video"


def test_explicit_duration_overrides_the_scene(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=1, beat="动作", duration=9)
    client = FakeMiniMax()

    generate_clip(
        content,
        page,
        make_story(),
        scene,
        client,
        duration=6,
        root=tmp_path,
    )

    assert client.request.duration == 6


def test_generate_clip_rejects_a_mismatched_scene(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=2, beat="动作")

    with pytest.raises(AssertionError):
        generate_clip(content, page, make_story(), scene, FakeMiniMax())


def test_generate_clip_stops_on_a_scene_error(tmp_path):
    content, page = make_content(tmp_path)
    scene = PageScene(index=1, beat="动作", error="no beat")
    client = FakeMiniMax()

    clip = generate_clip(
        content, page, make_story(), scene, client, root=tmp_path
    )

    assert clip.error == "no beat"
    assert client.request is None
    assert not clip_path("demo", "page_2.png", tmp_path).exists()


def make_book(root: Path, pages: int = 2) -> tuple[BookContent, Screenplay]:
    (root / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    items = [PageContent(index=0, filename="cover.png")]
    scenes = []
    for index in range(1, pages + 1):
        name = f"page_{index}.png"
        (root / name).write_bytes(b"\x89PNG\r\n\x1a\n")
        items.append(
            PageContent(index=index, filename=name, description="画面")
        )
        scenes.append(
            PageScene(index=index, beat=f"第 {index} 页动作", duration=6)
        )
    content = BookContent(id="demo", source=str(root), pages=items)
    return content, Screenplay(id="demo", pages=scenes)


def test_a_clip_survives_a_dict_round_trip():
    clip = VideoClip(
        index=3,
        filename="03.png",
        prompt="提示词",
        task_id="task-9",
        duration=9,
        resolution="1080P",
        path="clips/page_04.mp4",
    )

    assert VideoClip.from_dict(clip.to_dict()) == clip


def test_a_cached_clip_is_not_generated_twice(tmp_path):
    content, screenplay = make_book(tmp_path)
    cache = Cache(tmp_path / "cache")
    build_clips(
        content,
        make_story(),
        screenplay,
        FakeMiniMax(),
        cache=cache,
        root=tmp_path,
    )

    again = FakeMiniMax()
    clip_set = build_clips(
        content,
        make_story(),
        screenplay,
        again,
        cache=cache,
        root=tmp_path,
    )

    assert again.requests == []
    assert [clip.index for clip in clip_set.clips] == [1, 2]
    assert clip_set.failed_count == 0


def test_a_deleted_clip_file_is_generated_again(tmp_path):
    content, screenplay = make_book(tmp_path)
    cache = Cache(tmp_path / "cache")
    client = FakeMiniMax()
    build_clips(
        content,
        make_story(),
        screenplay,
        client,
        cache=cache,
        root=tmp_path,
    )
    clip_path("demo", "page_1.png", tmp_path).unlink()

    again = FakeMiniMax()
    build_clips(
        content,
        make_story(),
        screenplay,
        again,
        cache=cache,
        root=tmp_path,
    )

    assert len(again.requests) == 1
    assert clip_path("demo", "page_1.png", tmp_path).is_file()


def test_a_failed_clip_is_retried_next_run(tmp_path):
    content, screenplay = make_book(tmp_path)
    cache = Cache(tmp_path / "cache")
    first = build_clips(
        content,
        make_story(),
        screenplay,
        HalfFailingMiniMax(),
        cache=cache,
        root=tmp_path,
    )

    again = FakeMiniMax()
    build_clips(
        content,
        make_story(),
        screenplay,
        again,
        cache=cache,
        root=tmp_path,
    )

    assert first.failed_count == 1
    assert len(again.requests) == 1
