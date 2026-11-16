from pathlib import Path

import pytest

from aura_paper.minimax import (
    MiniMaxClient,
    MiniMaxError,
    VideoRequest,
    VideoTask,
)


def write_png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


def test_payload_builds_content(tmp_path):
    frame = write_png(tmp_path / "page.png")
    payload = VideoRequest(prompt="walk", first_frame=frame).to_payload("m")

    assert payload["model"] == "m"
    assert payload["duration"] == 6
    assert payload["resolution"] == "768P"
    assert "ratio" not in payload
    assert payload["content"][0] == {"type": "text", "text": "walk"}
    image = payload["content"][1]
    assert image["role"] == "first_frame"
    assert image["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("duration", [3, 16])
def test_payload_rejects_bad_duration(duration):
    with pytest.raises(ValueError, match="duration"):
        VideoRequest(prompt="walk", duration=duration)


def test_payload_rejects_mixed_inputs(tmp_path):
    frame = write_png(tmp_path / "page.png")

    with pytest.raises(ValueError, match="cannot be mixed"):
        VideoRequest(
            prompt="walk",
            first_frame=frame,
            reference_images=[frame],
        )


def test_payload_rejects_last_frame_without_first(tmp_path):
    frame = write_png(tmp_path / "page.png")

    with pytest.raises(ValueError, match="last_frame"):
        VideoRequest(prompt="walk", last_frame=frame)


def test_payload_rejects_oversized_image(monkeypatch, tmp_path):
    monkeypatch.setattr("aura_paper.minimax._MAX_IMAGE_BYTES", 1)
    target = tmp_path / "page.png"
    target.write_bytes(b"xx")

    with pytest.raises(ValueError, match="larger than 30MB"):
        VideoRequest(prompt="walk", first_frame=target)


def test_task_from_query_response():
    data = {
        "task": {
            "id": "424",
            "status": "succeeded",
            "content": {"url": "https://cdn/x.mp4"},
            "resolution": "2K",
            "duration": 5,
        }
    }

    task = VideoTask.from_response(data)

    assert task.task_id == "424"
    assert task.succeeded
    assert task.video_url == "https://cdn/x.mp4"
    assert task.resolution == "2K"
    assert task.duration == 5


def test_task_from_failed_response():
    data = {
        "task": {
            "id": "424",
            "status": "failed",
            "error": {"code": "1026", "message": "sensitive content"},
        }
    }

    task = VideoTask.from_response(data)

    assert task.done
    assert not task.succeeded
    assert task.error == "sensitive content"


def test_create_task_posts_payload(monkeypatch):
    client = MiniMaxClient(api_key="key")
    seen = {}

    def fake_post(path, payload):
        seen["path"] = path
        seen["payload"] = payload
        return {"task_id": "42"}

    monkeypatch.setattr(client, "_post", fake_post)
    task = client.create_task(VideoRequest(prompt="walk"))

    assert seen["path"] == "/v2/video_generation"
    assert seen["payload"]["model"] == "MiniMax-H3"
    assert task.task_id == "42"
    assert task.status == "queued"


def test_create_task_requires_task_id(monkeypatch):
    client = MiniMaxClient(api_key="key")
    monkeypatch.setattr(client, "_post", lambda path, payload: {})

    with pytest.raises(MiniMaxError, match="no task_id"):
        client.create_task(VideoRequest(prompt="walk"))


def test_wait_task_times_out(monkeypatch):
    client = MiniMaxClient(api_key="key", max_wait=0)
    monkeypatch.setattr(
        client,
        "get_task",
        lambda task_id: VideoTask(task_id, "running"),
    )

    task = client.wait_task("42")

    assert not task.done
    assert "timed out" in task.error


def test_download_writes_file(tmp_path):
    source = tmp_path / "src.mp4"
    source.write_bytes(b"video")
    target = tmp_path / "clips" / "page.mp4"
    client = MiniMaxClient(api_key="key")

    path = client.download(source.as_uri(), target)

    assert path.read_bytes() == b"video"
    assert not list(target.parent.glob("*.tmp"))


def test_check_raises_on_error_reply():
    client = MiniMaxClient(api_key="key")

    with pytest.raises(MiniMaxError, match="sensitive"):
        client._check({"error": {"message": "sensitive content"}})


def test_post_rejects_large_body(monkeypatch):
    monkeypatch.setattr("aura_paper.minimax._MAX_BODY_BYTES", 10)
    client = MiniMaxClient(api_key="key")

    with pytest.raises(ValueError, match="exceeds 64MB"):
        client._post("/x", {"prompt": "a" * 100})
