import io
import time
import urllib.error
import urllib.request
from email.message import Message

import pytest

from aura_paper.llm import LLMClient, LLMError


def test_chat_builds_payload(monkeypatch, sample_jpeg):
    captured = {}

    def fake_post(self, payload):
        captured.update(payload)
        return "reply"

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m")

    assert client.chat("describe", image_path=sample_jpeg) == "reply"

    system, user = captured["messages"]
    content = user["content"]
    assert captured["model"] == "m"
    assert "json" in system["content"].lower()
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[1]["text"] == "describe"
    assert captured["response_format"] == {"type": "json_object"}


def test_chat_without_json_mode(monkeypatch, sample_jpeg):
    captured = {}

    def fake_post(self, payload):
        captured.update(payload)
        return "ok"

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m")

    client.chat("hi", image_path=sample_jpeg, json_mode=False)

    assert "response_format" not in captured
    assert captured["messages"][0]["role"] == "user"


def test_chat_without_config_raises():
    client = LLMClient("", "", "")

    with pytest.raises(LLMError, match="not configured"):
        client.chat("hi")


def test_chat_without_image_sends_plain_text(monkeypatch):
    captured = {}

    def fake_post(self, payload):
        captured.update(payload)
        return "ok"

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m")

    client.chat("hello")

    assert captured["messages"][-1]["content"] == "hello"
    assert captured["response_format"] == {"type": "json_object"}


def test_chat_sends_the_reasoning_effort(monkeypatch):
    captured = {}

    def fake_post(self, payload):
        captured.update(payload)
        return "ok"

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m", reasoning_effort="low")

    client.chat("hello")

    assert captured["reasoning_effort"] == "low"


def test_chat_omits_an_unset_reasoning_effort(monkeypatch):
    captured = {}

    def fake_post(self, payload):
        captured.update(payload)
        return "ok"

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m")

    client.chat("hello")

    assert "reasoning_effort" not in captured


def test_from_env_uses_the_env_effort(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")

    client = LLMClient.from_env()

    assert client.reasoning_effort == "high"


def test_the_argument_wins_over_the_env_effort(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")

    client = LLMClient.from_env("low")

    assert client.reasoning_effort == "low"


def test_from_env_leaves_the_effort_empty(monkeypatch):
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)

    client = LLMClient.from_env()

    assert client.reasoning_effort == ""


class FakeResponse:
    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def fake_urlopen(monkeypatch, replies):
    calls = []

    def open_request(request, timeout=0):
        calls.append(request)
        reply = replies[min(len(calls), len(replies)) - 1]
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


def test_retries_while_the_endpoint_is_at_capacity(monkeypatch):
    calls = fake_urlopen(
        monkeypatch,
        [503, '{"choices": [{"message": {"content": "ok"}}]}'],
    )

    client = LLMClient("http://x/v1", "k", "m")

    assert client.chat("hello") == "ok"
    assert len(calls) == 2


def test_a_bad_request_is_not_retried(monkeypatch):
    calls = fake_urlopen(monkeypatch, [400])

    client = LLMClient("http://x/v1", "k", "m")

    with pytest.raises(LLMError, match="HTTP 400"):
        client.chat("hello")
    assert len(calls) == 1
