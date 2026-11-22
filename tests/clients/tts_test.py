import base64
import io
import json
import urllib.error

import pytest

from aura_paper.clients.tts import TTSClient, TTSError

# 24000 bytes of 16-bit mono at 24000 Hz is exactly half a second.
HALF_SECOND = b"\x01\x02" * 12000


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# One piece of the audio stream.
def chunk(pcm: bytes) -> dict:
    return {
        "code": 0,
        "message": "",
        "data": base64.b64encode(pcm).decode("ascii"),
    }


# The object that closes the stream.
def done(**overrides) -> dict:
    data = {"code": 20000000, "message": "ok", "data": None}
    data.update(overrides)
    return data


# Join reply objects the way the endpoint writes them.
def reply(*pieces: dict) -> str:
    return "\n".join(json.dumps(piece) for piece in pieces)


# Catch the request the client builds and answer with the given body.
def capture(monkeypatch, body: str) -> dict:
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["headers"] = {
            name.lower(): value for name, value in request.header_items()
        }
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(body.encode("utf-8"))

    monkeypatch.setattr(
        "aura_paper.clients.tts.urllib.request.urlopen", fake_urlopen
    )
    return seen


# A configured client pointing at the fake endpoint.
def client() -> TTSClient:
    return TTSClient(
        base_url="https://example/v3",
        api_key="key-1",
        resource_id="seed-tts-2.0",
    )


def test_sends_the_key_and_the_resource(monkeypatch):
    seen = capture(monkeypatch, reply(chunk(HALF_SECOND), done()))

    client().synthesize("三块、", voice="zh_female_xiaoxue_uranus_bigtts")

    assert seen["url"] == "https://example/v3/api/v3/tts/unidirectional"
    assert seen["headers"]["x-api-key"] == "key-1"
    assert seen["headers"]["x-api-resource-id"] == "seed-tts-2.0"
    assert "x-api-request-id" in seen["headers"]


def test_asks_for_pcm_at_the_default_rate(monkeypatch):
    seen = capture(monkeypatch, reply(chunk(HALF_SECOND), done()))

    client().synthesize("三块、", voice="BV051_streaming")

    request = seen["body"]["req_params"]
    assert request["text"] == "三块、"
    assert request["speaker"] == "BV051_streaming"
    assert request["audio_params"] == {"format": "pcm", "sample_rate": 24000}


def test_turns_a_speed_multiplier_into_a_percentage(monkeypatch):
    seen = capture(monkeypatch, reply(chunk(HALF_SECOND), done()))

    client().synthesize("三块、", voice="v", speed=0.9)

    assert seen["body"]["req_params"]["audio_params"]["speech_rate"] == -10


def test_leaves_the_rate_out_at_normal_speed(monkeypatch):
    seen = capture(monkeypatch, reply(chunk(HALF_SECOND), done()))

    client().synthesize("三块、", voice="v", speed=1.0)

    assert "speech_rate" not in seen["body"]["req_params"]["audio_params"]


def test_passes_an_emotion_when_given(monkeypatch):
    seen = capture(monkeypatch, reply(chunk(HALF_SECOND), done()))

    client().synthesize("三块、", voice="v", emotion="happy")

    assert seen["body"]["req_params"]["audio_params"]["emotion"] == "happy"


def test_joins_the_audio_pieces(monkeypatch):
    body = reply(
        chunk(HALF_SECOND[:12000]), chunk(HALF_SECOND[12000:]), done()
    )
    capture(monkeypatch, body)

    speech = client().synthesize("三块、", voice="v")

    # The reply is wrapped into one WAV file holding both pieces.
    assert speech.data[:4] == b"RIFF"
    assert speech.data[-len(HALF_SECOND) :] == HALF_SECOND
    assert speech.duration_ms == 500


def test_reports_a_failed_code(monkeypatch):
    body = reply({"code": 45000000, "message": "speaker permission denied"})
    capture(monkeypatch, body)

    with pytest.raises(TTSError) as error:
        client().synthesize("三块、", voice="v")

    assert "speaker permission denied" in str(error.value)


def test_reports_a_reply_without_audio(monkeypatch):
    capture(monkeypatch, reply(done()))

    with pytest.raises(TTSError) as error:
        client().synthesize("三块、", voice="v")

    assert "no audio" in str(error.value)


def test_reports_a_reply_that_is_not_json(monkeypatch):
    capture(monkeypatch, "抱歉，我看不清。")

    with pytest.raises(TTSError) as error:
        client().synthesize("三块、", voice="v")

    assert "not JSON" in str(error.value)


def test_reports_an_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key")
        )

    monkeypatch.setattr(
        "aura_paper.clients.tts.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(TTSError) as error:
        client().synthesize("三块、", voice="v")

    assert "HTTP 401" in str(error.value)


def test_reports_a_dead_endpoint(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(
        "aura_paper.clients.tts.urllib.request.urlopen", fake_urlopen
    )

    with pytest.raises(TTSError) as error:
        client().synthesize("三块、", voice="v")

    assert "cannot reach" in str(error.value)


def test_needs_an_empty_text_or_a_voice(monkeypatch):
    with pytest.raises(TTSError):
        client().synthesize("   ", voice="v")
    with pytest.raises(TTSError):
        client().synthesize("三块、", voice=" ")


def test_lists_the_missing_settings():
    client = TTSClient.from_env()

    assert client.missing_settings() == ["TTS_API_KEY", "TTS_RESOURCE_ID"]


def test_refuses_to_call_without_settings(monkeypatch):
    def fail(request, timeout=None):
        raise AssertionError("should not reach the endpoint")

    monkeypatch.setattr("aura_paper.clients.tts.urllib.request.urlopen", fail)

    with pytest.raises(TTSError) as error:
        TTSClient().synthesize("三块、", voice="v")

    assert "not configured" in str(error.value)


def test_writes_a_playable_file(monkeypatch, tmp_path):
    capture(monkeypatch, reply(chunk(HALF_SECOND), done()))
    speech = client().synthesize("三块、", voice="v")

    path = speech.save(tmp_path / "voice" / "j1-0.wav")

    assert path.is_file()
    assert path.read_bytes()[:4] == b"RIFF"
    assert path.stat().st_size == 44 + len(HALF_SECOND)
