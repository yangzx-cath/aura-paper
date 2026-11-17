from pathlib import Path

import pytest

from aura_paper.llm import LLMClient, LLMError

SAMPLE_JPG = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "chicken_and_sunflower"
    / "01.jpg"
)


def test_chat_builds_payload(monkeypatch):
    captured = {}

    def fake_post(self, payload):
        captured.update(payload)
        return "reply"

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m")

    assert client.chat("describe", image_path=SAMPLE_JPG) == "reply"

    system, user = captured["messages"]
    content = user["content"]
    assert captured["model"] == "m"
    assert "json" in system["content"].lower()
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[1]["text"] == "describe"
    assert captured["response_format"] == {"type": "json_object"}


def test_chat_without_json_mode(monkeypatch):
    captured = {}

    def fake_post(self, payload):
        captured.update(payload)
        return "ok"

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m")

    client.chat("hi", image_path=SAMPLE_JPG, json_mode=False)

    assert "response_format" not in captured
    assert captured["messages"][0]["role"] == "user"


def test_chat_without_config_raises():
    client = LLMClient("", "", "")

    with pytest.raises(LLMError, match="not configured"):
        client.chat("hi", image_path=SAMPLE_JPG)


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
