"""Tests for the request the chat client builds and how it fails."""

from __future__ import annotations

import http.client
import io
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest
from PIL import Image

from aura_paper.clients.llm import RETRIES, LLMClient, LLMError
from aura_paper.utils import data_url

REPLY = {"choices": [{"message": {"content": "{}"}}]}


class RecordingClient(LLMClient):
    """Client that keeps the payload instead of sending it."""

    def __init__(self, reply: dict = REPLY, effort: str = ""):
        super().__init__(
            "http://example/v1",
            "test-key",
            "fake-model",
            reasoning_effort=effort,
        )
        self.reply = reply
        self.payload: dict = {}

    def _send(self, payload: dict) -> dict:
        self.payload = payload
        return self.reply


class FakeResponse:
    """Minimal stand-in for the object urlopen returns."""

    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.body


# Write a small image of the given size so the files differ.
def make_image(path: Path, size: tuple[int, int]) -> Path:
    Image.new("RGB", size, "white").save(path)
    return path


# Replace urlopen with a script of replies and return the request list.
def fake_urlopen(monkeypatch, replies: list) -> list:
    calls: list = []

    def open_request(request, timeout=0):
        calls.append(request)
        reply = replies[min(len(calls), len(replies)) - 1]
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, int):
            raise urllib.error.HTTPError(
                request.full_url,
                reply,
                "error",
                Message(),
                io.BytesIO(b'{"error": "failed"}'),
            )
        return FakeResponse(reply)

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return calls


def test_sends_the_images_in_order_before_the_prompt(tmp_path: Path) -> None:
    first = make_image(tmp_path / "a.jpg", (4, 3))
    second = make_image(tmp_path / "b.jpg", (5, 3))
    client = RecordingClient()

    client.chat("读这一页", images=[first, second])

    content = client.payload["messages"][-1]["content"]
    assert [part["type"] for part in content] == [
        "image_url",
        "image_url",
        "text",
    ]
    assert content[0]["image_url"]["url"] == data_url(first)
    assert content[1]["image_url"]["url"] == data_url(second)
    assert content[2]["text"] == "读这一页"


def test_sends_plain_text_when_there_is_no_image() -> None:
    client = RecordingClient()

    client.chat("读这一页")

    assert client.payload["messages"][-1]["content"] == "读这一页"


def test_without_json_mode_leaves_out_the_system_turn() -> None:
    client = RecordingClient()

    client.chat("读这一页", json_mode=False)

    assert "response_format" not in client.payload
    assert client.payload["messages"][0]["role"] == "user"


def test_reports_a_cut_off_reply() -> None:
    reply = {
        "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]
    }
    client = RecordingClient(reply)

    with pytest.raises(LLMError, match="token limit"):
        client.chat("读这一页")


def test_chat_without_config_raises() -> None:
    client = LLMClient("", "", "")

    with pytest.raises(LLMError, match="not configured"):
        client.chat("读这一页")


def test_sends_the_effort_when_it_is_set() -> None:
    client = RecordingClient(effort="none")

    client.chat("读这一页")

    assert client.payload["reasoning_effort"] == "none"


def test_omits_the_effort_when_it_is_unset() -> None:
    client = RecordingClient()

    client.chat("读这一页")

    assert "reasoning_effort" not in client.payload


def test_the_effort_argument_wins_over_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")

    client = LLMClient.from_env("low")

    assert client.reasoning_effort == "low"


def test_from_env_reads_the_effort(monkeypatch) -> None:
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")

    client = LLMClient.from_env()

    assert client.reasoning_effort == "high"


def test_from_env_leaves_the_effort_empty(monkeypatch) -> None:
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)

    client = LLMClient.from_env()

    assert client.reasoning_effort == ""


def test_signature_carries_the_effort() -> None:
    client = LLMClient("http://x/v1", "k", "m", reasoning_effort="low")

    assert client.signature == ("m", "low")


def test_retries_while_the_endpoint_is_at_capacity(monkeypatch) -> None:
    calls = fake_urlopen(
        monkeypatch,
        [503, '{"choices": [{"message": {"content": "ok"}}]}'],
    )
    client = LLMClient("http://x/v1", "k", "m")

    assert client.chat("读这一页") == "ok"
    assert len(calls) == 2


def test_a_bad_request_is_not_retried(monkeypatch) -> None:
    calls = fake_urlopen(monkeypatch, [400])
    client = LLMClient("http://x/v1", "k", "m")

    with pytest.raises(LLMError, match="HTTP 400"):
        client.chat("读这一页")
    assert len(calls) == 1


def test_retries_a_reply_cut_off_mid_read(monkeypatch) -> None:
    calls = fake_urlopen(
        monkeypatch,
        [
            http.client.IncompleteRead(b'{"choi'),
            '{"choices": [{"message": {"content": "ok"}}]}',
        ],
    )
    client = LLMClient("http://x/v1", "k", "m")

    assert client.chat("读这一页") == "ok"
    assert len(calls) == 2


def test_a_reply_that_keeps_dropping_ends_as_an_error(monkeypatch) -> None:
    calls = fake_urlopen(monkeypatch, [ConnectionResetError("reset")])
    client = LLMClient("http://x/v1", "k", "m")

    with pytest.raises(LLMError, match="dropped connection"):
        client.chat("读这一页")
    assert len(calls) == RETRIES
