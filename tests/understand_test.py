import json
from pathlib import Path

from book import PageImage
from understand import understand_page
from vision import VisionClient, VisionError


class FakeClient(VisionClient):
    def __init__(self, reply="", error=None):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.reply = reply
        self.error = error
        self.prompts = []

    def analyze(
        self,
        prompt: str,
        image_path: Path,
        *,
        json_mode: bool = True,
    ) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def make_page(kind="single"):
    return PageImage(
        index=3,
        filename="03.jpg",
        path="data/chicken_and_sunflower/03.jpg",
        kind=kind,
    )


def test_success():
    reply = json.dumps(
        {"page_text": "你好", "description": "草地", "mood": "温暖"}
    )

    content = understand_page(make_page(), FakeClient(reply))

    assert content.index == 3
    assert content.filename == "03.jpg"
    assert content.model == "fake-model"
    assert content.page_text == "你好"
    assert content.description == "草地"
    assert content.mood == "温暖"
    assert content.error == ""


def test_vision_error_is_recorded():
    client = FakeClient(error=VisionError("boom"))

    content = understand_page(make_page(), client)

    assert content.error == "boom"
    assert content.page_text == ""


def test_bad_json_is_recorded():
    content = understand_page(make_page(), FakeClient("抱歉，我做不到"))

    assert "no JSON object" in content.error


def test_null_field_becomes_empty():
    reply = json.dumps({"page_text": None, "description": "草地"})

    content = understand_page(make_page(), FakeClient(reply))

    assert content.page_text == ""
    assert content.description == "草地"
    assert content.error == ""


def test_empty_payload_is_an_error():
    content = understand_page(make_page(), FakeClient("{}"))

    assert content.error == "model returned no content"


def test_spread_page_uses_spread_prompt():
    client = FakeClient(json.dumps({"page_text": "文字"}))

    understand_page(make_page(kind="spread"), client)

    assert "跨页" in client.prompts[0]
