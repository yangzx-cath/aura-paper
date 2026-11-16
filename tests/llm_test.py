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


def test_chat_propagates_llm_error(monkeypatch):
    def fake_post(self, payload):
        raise LLMError("boom")

    monkeypatch.setattr(LLMClient, "_post", fake_post)
    client = LLMClient("http://x/v1", "k", "m")

    with pytest.raises(LLMError, match="boom"):
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


def test_chat_rejects_unsupported_image(tmp_path):
    target = tmp_path / "page.xyz"
    target.write_bytes(b"x")
    client = LLMClient("http://x/v1", "k", "m")

    with pytest.raises(ValueError, match="unsupported image type"):
        client.chat("hi", image_path=target)
