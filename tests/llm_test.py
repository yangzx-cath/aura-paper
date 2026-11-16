import base64
from pathlib import Path

import pytest

from aura_paper.llm import LLMClient, LLMError
from aura_paper.utils import data_url, extract_json

SAMPLE_JPG = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "chicken_and_sunflower"
    / "01.jpg"
)


def test_jpeg_prefix_and_payload():
    url = data_url(SAMPLE_JPG)

    header, _, payload = url.partition(",")
    assert header == "data:image/jpeg;base64"
    assert base64.b64decode(payload) == SAMPLE_JPG.read_bytes()


def test_png_uses_png_mime(tmp_path):
    target = tmp_path / "page.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")

    url = data_url(target)

    assert url.startswith("data:image/png;base64,")


def test_bmp_uses_bmp_mime(tmp_path):
    target = tmp_path / "page.bmp"
    target.write_bytes(b"BM fake")

    url = data_url(target)

    assert url.startswith("data:image/bmp;base64,")


def test_unknown_suffix_raises(tmp_path):
    target = tmp_path / "page.xyz"
    target.write_bytes(b"whatever")

    with pytest.raises(ValueError, match="unsupported image type"):
        data_url(target)


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_after_prose():
    assert extract_json('结果如下：\n{"a": 1}\n以上') == {"a": 1}


def test_extract_takes_first_object():
    assert extract_json('{"a": 1}\n{"b": 2}') == {"a": 1}


def test_extract_without_json_raises():
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json("抱歉，我无法完成")


def test_extract_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")


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
