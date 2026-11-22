import base64
import io
import json
import urllib.error

import pytest

from aura_paper.tts import (
    DEFAULT_CLUSTER,
    DEFAULT_VOICE,
    TTSClient,
    TTSError,
)


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(**overrides) -> dict:
    data = {
        "reqid": "r1",
        "code": 3000,
        "message": "Success",
        "sequence": -1,
        "data": base64.b64encode(b"audio").decode("ascii"),
        "addition": {"duration": "1960"},
    }
    data.update(overrides)
    return data


def client() -> TTSClient:
    return TTSClient(app_id="app", token="secret")


def test_payload_carries_app_user_audio_and_request():
    payload = client()._payload("你好", "voice-1", "", 1.0)

    assert payload["app"] == {
        "appid": "app",
        "token": "secret",
        "cluster": DEFAULT_CLUSTER,
    }
    assert payload["user"]["uid"]
    assert payload["audio"]["voice_type"] == "voice-1"
    assert payload["audio"]["encoding"] == "mp3"
    assert "emotion" not in payload["audio"]
    assert payload["request"]["text"] == "你好"
    assert payload["request"]["operation"] == "query"
    assert payload["request"]["text_type"] == "plain"


def test_payload_keeps_emotion_and_speed():
    payload = client()._payload("你好", "voice-1", "angry", 1.2)

    assert payload["audio"]["emotion"] == "angry"
    assert payload["audio"]["speed_ratio"] == 1.2


def test_each_payload_gets_its_own_request_id():
    first = client()._payload("a", DEFAULT_VOICE, "", 1.0)
    second = client()._payload("a", DEFAULT_VOICE, "", 1.0)

    assert first["request"]["reqid"] != second["request"]["reqid"]


def test_synthesize_returns_the_audio_and_its_length(monkeypatch):
    client_ = client()
    monkeypatch.setattr(client_, "_post", lambda payload: reply())

    speech = client_.synthesize("你好")

    assert speech.data == b"audio"
    assert speech.duration_ms == 1960
    assert speech.voice == DEFAULT_VOICE
    assert speech.text == "你好"


def test_synthesize_uses_the_voice_of_this_call(monkeypatch):
    client_ = client()
    seen = {}

    def fake_post(payload):
        seen["voice"] = payload["audio"]["voice_type"]
        return reply()

    monkeypatch.setattr(client_, "_post", fake_post)

    speech = client_.synthesize("你好", voice="voice-x")

    assert seen["voice"] == "voice-x"
    assert speech.voice == "voice-x"


def test_synthesize_rejects_empty_text():
    with pytest.raises(TTSError, match="text is required"):
        client().synthesize("   ")


def test_a_non_success_code_becomes_an_error(monkeypatch):
    client_ = client()
    monkeypatch.setattr(
        client_,
        "_post",
        lambda payload: reply(code=3010, message="text too long"),
    )

    with pytest.raises(TTSError, match="text too long"):
        client_.synthesize("你好")


def test_a_reply_without_audio_becomes_an_error(monkeypatch):
    client_ = client()
    monkeypatch.setattr(client_, "_post", lambda payload: reply(data=""))

    with pytest.raises(TTSError, match="no audio"):
        client_.synthesize("你好")


def test_audio_that_is_not_base64_becomes_an_error(monkeypatch):
    client_ = client()
    monkeypatch.setattr(
        client_, "_post", lambda payload: reply(data="***not base64***")
    )

    with pytest.raises(TTSError, match="not base64"):
        client_.synthesize("你好")


def test_a_reply_without_a_length_reports_zero(monkeypatch):
    client_ = client()
    monkeypatch.setattr(client_, "_post", lambda payload: reply(addition={}))

    assert client_.synthesize("你好").duration_ms == 0


def test_send_raises_when_the_endpoint_is_not_configured(monkeypatch):
    with pytest.raises(TTSError, match="not configured"):
        TTSClient(app_id="app")._send(b"{}")


def test_send_posts_with_the_semicolon_authorization(monkeypatch):
    seen = {}
    body = json.dumps(reply()).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = request.data
        return FakeResponse(body)

    monkeypatch.setattr("aura_paper.tts.urllib.request.urlopen", fake_urlopen)

    client()._send(b'{"a":1}')

    assert seen["url"] == "https://openspeech.bytedance.com/api/v1/tts"
    assert seen["auth"] == "Bearer;secret"
    assert seen["body"] == b'{"a":1}'


def test_an_http_error_carries_the_reply_body(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            "http://x",
            401,
            "unauthorized",
            {},
            io.BytesIO(b'{"message":"bad token"}'),
        )

    monkeypatch.setattr("aura_paper.tts.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(TTSError, match="bad token"):
        client()._send(b"{}")


def test_a_reply_that_is_not_json_becomes_an_error(monkeypatch):
    monkeypatch.setattr(
        "aura_paper.tts.urllib.request.urlopen",
        lambda request, timeout: FakeResponse(b"<html>"),
    )

    with pytest.raises(TTSError, match="not JSON"):
        client()._send(b"{}")


def test_from_env_reads_the_settings(monkeypatch):
    monkeypatch.setenv("TTS_APP_ID", "app-2")
    monkeypatch.setenv("TTS_ACCESS_TOKEN", "token-2")
    monkeypatch.setenv("TTS_VOICE", "voice-2")
    monkeypatch.setenv("TTS_CLUSTER", "cluster-2")
    monkeypatch.delenv("TTS_BASE_URL", raising=False)

    client_ = TTSClient.from_env()

    assert client_.app_id == "app-2"
    assert client_.token == "token-2"
    assert client_.voice == "voice-2"
    assert client_.cluster == "cluster-2"
    assert client_.base_url.startswith("https://")


def test_missing_settings_lists_the_empty_keys():
    assert TTSClient().missing_settings() == [
        "TTS_APP_ID",
        "TTS_ACCESS_TOKEN",
    ]
    assert TTSClient(app_id="app", token="secret").missing_settings() == []


def test_speech_save_writes_the_file(tmp_path):
    client_ = client()
    path = tmp_path / "line.mp3"

    speech = client_._speech(
        "你好", client_._payload("你好", "v", "", 1.0), reply()
    )
    speech.save(path)

    assert path.read_bytes() == b"audio"
