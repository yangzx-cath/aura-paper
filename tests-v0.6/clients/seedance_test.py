import io
import urllib.error
from pathlib import Path

import pytest
from aura_paper.clients.seedance import (
    DEFAULT_MODEL,
    SeedanceClient,
    SeedanceError,
)
from aura_paper.clients.video import VideoRequest, VideoTask


def write_png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


class FakeResponse:
    def __init__(self, body: bytes, length: int | None = None) -> None:
        self.body = body
        self.headers = {}
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            data, self.body = self.body, b""
            return data
        data, self.body = self.body[:size], self.body[size:]
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://x",
        code,
        "error",
        {},
        io.BytesIO(body),
    )


def test_payload_builds_reference_content(tmp_path):
    page = write_png(tmp_path / "page.png")
    payload = SeedanceClient(api_key="key")._payload(
        VideoRequest(prompt="walk", reference_images=[page])
    )

    assert payload["model"] == DEFAULT_MODEL
    assert payload["duration"] == 6
    assert payload["resolution"] == "720p"
    assert "generate_audio" not in payload
    assert "ratio" not in payload
    assert payload["content"][0] == {"type": "text", "text": "walk"}
    image = payload["content"][1]
    assert image["role"] == "reference_image"
    assert image["image_url"]["url"].startswith("data:image/png;base64,")


def test_payload_keeps_first_frame_role(tmp_path):
    page = write_png(tmp_path / "page.png")
    payload = SeedanceClient(api_key="key")._payload(
        VideoRequest(prompt="walk", first_frame=page)
    )

    assert payload["content"][1]["role"] == "first_frame"


def test_payload_normalizes_a_resolution_preset():
    payload = SeedanceClient(api_key="key")._payload(
        VideoRequest(prompt="walk", resolution="720P")
    )

    assert payload["resolution"] == "720p"


def test_payload_includes_ratio_when_set():
    payload = SeedanceClient(api_key="key")._payload(
        VideoRequest(prompt="walk", ratio="9:16")
    )

    assert payload["ratio"] == "9:16"


def test_payload_rejects_an_unknown_resolution():
    client = SeedanceClient(api_key="key")

    with pytest.raises(ValueError, match="unsupported resolution"):
        client._payload(VideoRequest(prompt="walk", resolution="2K"))


def test_payload_rejects_oversized_image(monkeypatch, tmp_path):
    monkeypatch.setattr("aura_paper.clients.seedance._MAX_IMAGE_BYTES", 1)
    target = tmp_path / "page.png"
    target.write_bytes(b"xx")

    with pytest.raises(ValueError, match="larger than 30MB"):
        SeedanceClient(api_key="key")._payload(
            VideoRequest(prompt="walk", reference_images=[target])
        )


def test_create_task_posts_payload(monkeypatch):
    client = SeedanceClient(api_key="key")
    seen = {}

    def fake_post(path, payload, *, timeout):
        seen["path"] = path
        seen["payload"] = payload
        seen["timeout"] = timeout
        return {"id": "cgt-1"}

    monkeypatch.setattr(client, "_post", fake_post)
    task = client.create_task(VideoRequest(prompt="walk"))

    assert seen["path"] == "/contents/generations/tasks"
    assert seen["payload"]["model"] == DEFAULT_MODEL
    assert "generate_audio" not in seen["payload"]
    assert task.task_id == "cgt-1"
    assert task.status == "queued"


def test_create_task_requires_task_id(monkeypatch):
    client = SeedanceClient(api_key="key")
    monkeypatch.setattr(client, "_post", lambda path, payload, *, timeout: {})

    with pytest.raises(SeedanceError, match="no task_id"):
        client.create_task(VideoRequest(prompt="walk"))


def test_task_from_query_response():
    data = {
        "id": "cgt-1",
        "status": "succeeded",
        "content": {"video_url": "https://cdn/x.mp4"},
        "resolution": "720p",
        "duration": 5,
    }

    task = SeedanceClient._task_from(data)

    assert task.task_id == "cgt-1"
    assert task.succeeded
    assert task.video_url == "https://cdn/x.mp4"
    assert task.resolution == "720p"
    assert task.duration == 5


def test_task_from_failed_response():
    data = {
        "id": "cgt-1",
        "status": "failed",
        "error": {
            "code": "InvalidParameter",
            "message": "bad ratio",
        },
    }

    task = SeedanceClient._task_from(data)

    assert task.done
    assert not task.succeeded
    assert task.error == "InvalidParameter: bad ratio"


def test_an_expired_task_is_done():
    task = SeedanceClient._task_from({"id": "cgt-1", "status": "expired"})

    assert task.done
    assert not task.succeeded
    assert not task.pending


def test_get_task_quotes_the_task_id(monkeypatch):
    client = SeedanceClient(api_key="key")
    seen = {}

    def fake_get(path, params):
        seen["path"] = path
        return {"id": "a/b", "status": "running"}

    monkeypatch.setattr(client, "_get", fake_get)
    task = client.get_task("a/b")

    assert seen["path"] == "/contents/generations/tasks/a%2Fb"
    assert task.status == "running"


def test_wait_task_times_out(monkeypatch):
    client = SeedanceClient(api_key="key", max_wait=0)
    monkeypatch.setattr(
        client,
        "get_task",
        lambda task_id: VideoTask(task_id, "running"),
    )

    task = client.wait_task("cgt-1")

    assert not task.done
    assert "timed out" in task.error


def test_wait_task_retries_a_failed_poll(monkeypatch):
    client = SeedanceClient(api_key="key", poll_interval=0)
    replies = [
        SeedanceError("poll timed out"),
        VideoTask("cgt-1", "succeeded"),
    ]

    def get_task(task_id):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(client, "get_task", get_task)

    task = client.wait_task("cgt-1")

    assert task.done
    assert replies == []


def test_wait_task_gives_up_after_three_failed_polls(monkeypatch):
    client = SeedanceClient(api_key="key", poll_interval=0)
    calls = []

    def get_task(task_id):
        calls.append(1)
        raise SeedanceError("poll timed out")

    monkeypatch.setattr(client, "get_task", get_task)

    with pytest.raises(SeedanceError, match="poll timed out"):
        client.wait_task("cgt-1")

    assert len(calls) == 3


def test_wait_task_returns_a_failed_task(monkeypatch):
    client = SeedanceClient(api_key="key")
    monkeypatch.setattr(
        client,
        "get_task",
        lambda task_id: VideoTask(task_id, "failed", error="boom"),
    )

    task = client.wait_task("cgt-1")

    assert task.done
    assert task.error == "boom"


def test_download_writes_file(tmp_path):
    source = tmp_path / "src.mp4"
    source.write_bytes(b"video")
    target = tmp_path / "clips" / "page.mp4"
    client = SeedanceClient(api_key="key")

    path = client.download(source.as_uri(), target)

    assert path.read_bytes() == b"video"
    assert not list(target.parent.glob("*.tmp"))


def test_check_raises_on_error_reply():
    client = SeedanceClient(api_key="key")

    with pytest.raises(SeedanceError, match="InvalidParameter: bad"):
        client._check(
            {
                "error": {
                    "code": "InvalidParameter",
                    "message": "bad",
                }
            }
        )


def test_post_rejects_a_large_body(monkeypatch):
    monkeypatch.setattr("aura_paper.clients.seedance._MAX_BODY_BYTES", 10)
    client = SeedanceClient(api_key="key")

    with pytest.raises(ValueError, match="exceeds 64MB"):
        client._post("/x", {"prompt": "a" * 100}, timeout=client.timeout)


def test_from_env_prefers_ark_api_key(monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "ark-key")
    monkeypatch.setenv("SEEDANCE_MODEL", "model-x")
    monkeypatch.delenv("SEEDANCE_BASE_URL", raising=False)

    client = SeedanceClient.from_env()

    assert client.api_key == "ark-key"
    assert client.model == "model-x"
    assert client.base_url.startswith("https://ark.")


def test_missing_settings_names_the_ark_key():
    assert SeedanceClient().missing_settings() == ["ARK_API_KEY"]
    assert SeedanceClient(api_key="key").missing_settings() == []


def test_generate_reports_a_missing_video_url(monkeypatch, tmp_path):
    client = SeedanceClient(api_key="key")
    monkeypatch.setattr(
        client,
        "create_task",
        lambda request: VideoTask("cgt-1", "queued"),
    )
    monkeypatch.setattr(
        client,
        "wait_task",
        lambda task_id: VideoTask(task_id, "succeeded"),
    )

    target = tmp_path / "out" / "clip.mp4"
    task = client.generate(VideoRequest(prompt="walk"), target)

    assert task.error == "task succeeded without a video URL"
    assert not target.exists()


def test_generate_returns_a_failed_task_without_download(
    monkeypatch, tmp_path
):
    client = SeedanceClient(api_key="key")
    calls = []

    monkeypatch.setattr(
        client,
        "create_task",
        lambda request: VideoTask("cgt-1", "queued"),
    )
    monkeypatch.setattr(
        client,
        "wait_task",
        lambda task_id: VideoTask(task_id, "failed", error="boom"),
    )
    monkeypatch.setattr(client, "download", lambda *args: calls.append(args))

    task = client.generate(VideoRequest(prompt="walk"), tmp_path / "clip.mp4")

    assert task.error == "boom"
    assert calls == []


def test_send_wraps_an_http_error_message(monkeypatch):
    client = SeedanceClient(api_key="key")
    body = b'{"error":{"code":"InvalidParameter","message":"bad"}}'

    def fake_urlopen(*args, **kwargs):
        raise http_error(400, body)

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="InvalidParameter: bad"):
        client._get("/x", {})


def test_send_falls_back_to_the_http_status(monkeypatch):
    client = SeedanceClient(api_key="key")

    def fake_urlopen(*args, **kwargs):
        raise http_error(503, b'{"error":{}}')

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="HTTP 503"):
        client._get("/x", {})


def test_send_wraps_a_connection_error(monkeypatch):
    client = SeedanceClient(api_key="key")

    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="cannot reach"):
        client._get("/x", {})


def test_send_wraps_a_timeout(monkeypatch):
    client = SeedanceClient(api_key="key", timeout=3)

    def fake_urlopen(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="poll timed out after 3s"):
        client._get("/x", {})


def test_send_rejects_a_non_json_reply(monkeypatch):
    client = SeedanceClient(api_key="key")
    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(b"<html>"),
    )

    with pytest.raises(SeedanceError, match="malformed reply"):
        client._get("/x", {})


def test_send_rejects_a_non_object_reply(monkeypatch):
    client = SeedanceClient(api_key="key")
    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(b"[]"),
    )

    with pytest.raises(SeedanceError, match="malformed reply"):
        client._get("/x", {})


def test_send_requires_an_api_key():
    client = SeedanceClient()

    with pytest.raises(SeedanceError, match="not configured"):
        client._post("/x", {"prompt": "walk"}, timeout=client.timeout)


def test_task_from_rejects_a_malformed_reply():
    with pytest.raises(SeedanceError, match="malformed task reply"):
        SeedanceClient._task_from({"task": []})


def test_download_wraps_an_http_error(monkeypatch, tmp_path):
    client = SeedanceClient(api_key="key")
    target = tmp_path / "clip.mp4"
    monkeypatch.setattr("aura_paper.clients.seedance.RETRY_DELAYS", ())

    def fake_urlopen(*args, **kwargs):
        raise http_error(404, b"")

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="download HTTP 404"):
        client.download("http://x/clip.mp4", target)

    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_download_wraps_a_connection_error(monkeypatch, tmp_path):
    client = SeedanceClient(api_key="key")
    target = tmp_path / "clip.mp4"
    monkeypatch.setattr("aura_paper.clients.seedance.RETRY_DELAYS", ())

    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="cannot download video"):
        client.download("http://x/clip.mp4", target)

    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_download_retries_a_stalled_transfer(monkeypatch, tmp_path):
    client = SeedanceClient(api_key="key")
    target = tmp_path / "clip.mp4"
    waits = []
    attempts = []

    def fake_urlopen(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("stalled")
        return FakeResponse(b"video")

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )
    monkeypatch.setattr("aura_paper.clients.seedance.time.sleep", waits.append)

    path = client.download("http://x/clip.mp4", target)

    assert path.read_bytes() == b"video"
    assert waits == [2.0]
    assert len(attempts) == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_download_rejects_a_body_shorter_than_promised(monkeypatch, tmp_path):
    client = SeedanceClient(api_key="key")
    target = tmp_path / "clip.mp4"
    monkeypatch.setattr("aura_paper.clients.seedance.RETRY_DELAYS", ())

    def fake_urlopen(*args, **kwargs):
        return FakeResponse(b"vide", length=10)

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="stopped at 4 of 10 bytes"):
        client.download("http://x/clip.mp4", target)

    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_download_wraps_a_broken_stream(monkeypatch, tmp_path):
    client = SeedanceClient(api_key="key")
    target = tmp_path / "clip.mp4"
    monkeypatch.setattr("aura_paper.clients.seedance.RETRY_DELAYS", ())

    def fake_urlopen(*args, **kwargs):
        raise ConnectionResetError("reset")

    monkeypatch.setattr(
        "aura_paper.clients.seedance.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(SeedanceError, match="download failed"):
        client.download("http://x/clip.mp4", target)
