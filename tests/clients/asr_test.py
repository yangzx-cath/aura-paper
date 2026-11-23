import asyncio
import gzip
import json

import pytest

from aura_paper.clients import asr
from aura_paper.clients.asr import (
    FLAG_LAST,
    FLAG_NONE,
    FLAG_SEQUENCE,
    FULL_REQUEST,
    ASRClient,
    ASRError,
    Hearing,
)

# 6400 bytes of 16-bit mono at 16 kHz is one fifth of a second.
SLICE = b"\x01\x02" * 3200

# The text the fake endpoint reports for a line.
SPOKEN = "小满在哪里？"


# Build one reply of the endpoint, as a binary websocket frame.
def reply(payload: dict, *, flags: int = FLAG_SEQUENCE) -> bytes:
    body = gzip.compress(json.dumps(payload, ensure_ascii=False).encode())
    head = bytes([0x11, (0b1001 << 4) | flags, 0x11, 0x00])
    sequence = (
        b"\x00\x00\x00\x01" if flags in (FLAG_SEQUENCE, FLAG_LAST) else b""
    )
    return head + sequence + len(body).to_bytes(4, "big") + body


# Build one error reply of the endpoint.
def failure(code: int, message: str) -> bytes:
    body = json.dumps({"error": message}).encode()
    head = bytes([0x11, (0b1111 << 4) | FLAG_NONE, 0x01, 0x00])
    return head + code.to_bytes(4, "big") + len(body).to_bytes(4, "big") + body


# The reply that carries the text so far.
def partial(text: str) -> dict:
    return {"result": {"text": text}}


# The reply that closes the line.
def final(text: str, *, duration: int = 2000, label: str = "") -> dict:
    additions = {} if not label else {"lid_lang": label}
    return {
        "audio_info": {"duration": duration},
        "result": {
            "text": text,
            "utterances": [{"definite": True, "additions": additions}],
        },
    }


# The reply that closes the line.
def closing(text: str, *, duration: int = 2000, label: str = "") -> bytes:
    return reply(final(text, duration=duration, label=label), flags=FLAG_LAST)


# Read back one frame the client sent.
def unpack(message: bytes) -> tuple[int, int, int | None, bytes]:
    kind = message[1] >> 4
    flags = message[1] & 0x0F
    at = (message[0] & 0x0F) * 4
    sequence = None
    if flags in (FLAG_SEQUENCE, FLAG_LAST):
        sequence = int.from_bytes(message[at : at + 4], "big", signed=True)
        at += 4
    size = int.from_bytes(message[at : at + 4], "big")
    at += 4
    return kind, flags, sequence, gzip.decompress(message[at : at + size])


# Stand in for one open websocket.
class FakeSocket:
    def __init__(self, replies: list, after: int = 0) -> None:
        self.replies = list(replies)
        self.after = after
        self.sent: list[bytes] = []

    async def __aenter__(self) -> "FakeSocket":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def send(self, message: bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> bytes:
        # A real endpoint answers while the audio arrives; a test that
        # cares about what was sent waits for all of it first.
        while len(self.sent) < self.after:
            await asyncio.sleep(0)
        if not self.replies:
            raise asyncio.TimeoutError
        answer = self.replies.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


# Answer each connection with the next socket, which may be reused.
def capture(monkeypatch, *sockets: FakeSocket) -> list:
    opened = []
    queue = list(sockets)

    def fake_connect(url, headers):
        socket = queue[min(len(opened), len(queue) - 1)]
        opened.append((url, headers, socket))
        return socket

    monkeypatch.setattr("aura_paper.clients.asr._connect", fake_connect)
    monkeypatch.setattr(asr.time, "sleep", lambda seconds: None)
    return opened


# A configured client pointing at the fake endpoint.
def client() -> ASRClient:
    return ASRClient(
        base_url="wss://example/v3/sauc/bigmodel_async",
        api_key="key-1",
        resource_id="volc.seedasr.sauc.duration",
    )


def test_turns_the_audio_into_text(monkeypatch):
    socket = FakeSocket([reply(partial("小满")), closing(SPOKEN)])
    capture(monkeypatch, socket)

    hearing = client().transcribe(SLICE)

    assert hearing == Hearing(SPOKEN, "zh", 2000)


def test_opens_the_endpoint_with_the_key_and_the_resource(monkeypatch):
    opened = capture(monkeypatch, FakeSocket([closing(SPOKEN)]))

    client().transcribe(SLICE)

    url, headers, _ = opened[0]
    assert url == "wss://example/v3/sauc/bigmodel_async"
    assert headers["X-Api-Key"] == "key-1"
    assert headers["X-Api-Resource-Id"] == "volc.seedasr.sauc.duration"
    assert "X-Api-Request-Id" in headers
    assert "X-Api-Connect-Id" in headers


def test_says_what_the_audio_is_before_sending_it(monkeypatch):
    socket = FakeSocket([closing(SPOKEN)])
    capture(monkeypatch, socket)

    client().transcribe(SLICE)

    kind, _, _, body = unpack(socket.sent[0])
    config = json.loads(body)
    assert kind == FULL_REQUEST
    assert config["audio"] == {
        "format": "pcm",
        "rate": 16000,
        "bits": 16,
        "channel": 1,
    }
    assert config["request"]["model_name"] == "bigmodel"
    assert config["request"]["enable_lid"] is True


def test_closes_the_stream_with_a_negative_sequence(monkeypatch):
    socket = FakeSocket([closing(SPOKEN)], after=4)
    capture(monkeypatch, socket)

    client().transcribe(SLICE * 3)

    frames = [unpack(message) for message in socket.sent[1:]]
    assert [flags for _, flags, _, _ in frames] == [
        FLAG_SEQUENCE,
        FLAG_SEQUENCE,
        FLAG_LAST,
    ]
    assert [sequence for _, _, sequence, _ in frames] == [2, 3, -4]


def test_sends_the_hotwords_with_the_request(monkeypatch):
    socket = FakeSocket([closing(SPOKEN)])
    capture(monkeypatch, socket)

    client().transcribe(SLICE, hotwords=("小满", "花花"))

    _, _, _, body = unpack(socket.sent[0])
    context = json.loads(json.loads(body)["request"]["corpus"]["context"])
    assert context == {"hotwords": [{"word": "小满"}, {"word": "花花"}]}


def test_reads_the_language_the_endpoint_heard(monkeypatch):
    socket = FakeSocket([closing("Where are you?", label="speech_en")])
    capture(monkeypatch, socket)

    hearing = client().transcribe(SLICE)

    assert hearing.language == "en"


def test_falls_back_to_the_words_when_no_language_is_reported(monkeypatch):
    socket = FakeSocket([closing("Where are you?")])
    capture(monkeypatch, socket)

    hearing = client().transcribe(SLICE)

    assert hearing.language == "en"


def test_reports_the_text_as_it_grows(monkeypatch):
    socket = FakeSocket(
        [reply(partial("小满")), reply(partial(SPOKEN)), closing(SPOKEN)]
    )
    capture(monkeypatch, socket)
    seen: list[str] = []

    client().transcribe(SLICE, on_text=seen.append)

    assert seen == ["小满", SPOKEN]


def test_listens_to_a_live_stream(monkeypatch):
    socket = FakeSocket([reply(partial("小满")), closing(SPOKEN)], after=4)
    capture(monkeypatch, socket)
    seen: list[str] = []

    async def microphone():
        for _ in range(3):
            yield SLICE

    hearing = asyncio.run(client().listen(microphone(), on_text=seen.append))

    assert hearing.text == SPOKEN
    assert seen == ["小满", SPOKEN]
    assert len(socket.sent) == 4


def test_reports_a_rejected_request(monkeypatch):
    capture(
        monkeypatch,
        FakeSocket([failure(45000000, "decode ws request failed")]),
    )

    with pytest.raises(ASRError) as error:
        client().transcribe(SLICE)

    assert "45000000" in str(error.value)
    assert "decode ws request failed" in str(error.value)


def test_asks_again_when_the_service_is_busy(monkeypatch):
    busy = FakeSocket([failure(55000031, "server is busy")])
    spoken = FakeSocket([closing(SPOKEN)])
    opened = capture(monkeypatch, busy, spoken)

    hearing = client().transcribe(SLICE)

    assert hearing.text == SPOKEN
    assert len(opened) == 2


def test_gives_up_after_the_last_attempt(monkeypatch):
    busy = FakeSocket([failure(55000031, "server is busy")] * asr.RETRIES)
    opened = capture(monkeypatch, busy)

    with pytest.raises(ASRError) as error:
        client().transcribe(SLICE)

    assert "busy" in str(error.value)
    assert len(opened) == asr.RETRIES


def test_reports_a_stream_that_stops_answering(monkeypatch):
    opened = capture(monkeypatch, FakeSocket([]))

    with pytest.raises(ASRError) as error:
        client().transcribe(SLICE)

    assert "timeout" in str(error.value)
    assert len(opened) == 1


def test_needs_audio(monkeypatch):
    with pytest.raises(ASRError):
        client().transcribe(b"")


def test_needs_a_key_and_a_resource(monkeypatch):
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    monkeypatch.delenv("TTS_API_KEY", raising=False)
    monkeypatch.delenv("ASR_RESOURCE_ID", raising=False)

    missing = asr.ASRClient.from_env().missing_settings()

    assert missing == ["ASR_API_KEY", "ASR_RESOURCE_ID"]


def test_reads_the_key_from_the_tts_setting(monkeypatch):
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    monkeypatch.setenv("TTS_API_KEY", "key-shared")
    monkeypatch.setenv("ASR_RESOURCE_ID", "volc.seedasr.sauc.duration")

    client_from_env = asr.ASRClient.from_env()

    assert client_from_env.api_key == "key-shared"
    assert client_from_env.missing_settings() == []
