import json
from pathlib import Path

from book import Book, PageImage
from understand import understand_book, understand_page
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


class SequenceClient(FakeClient):
    def __init__(self, replies):
        super().__init__()
        self.replies = list(replies)

    def analyze(
        self,
        prompt: str,
        image_path: Path,
        *,
        json_mode: bool = True,
    ) -> str:
        self.prompts.append(prompt)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_page(kind="single"):
    return PageImage(
        index=3,
        filename="03.jpg",
        path="data/chicken_and_sunflower/03.jpg",
        kind=kind,
    )


def make_book(pages):
    book = Book("chicken", title="小鸡球球")
    book.source = "/tmp/chicken"
    book.pages = pages
    return book


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


def test_book_collects_every_page():
    reply = json.dumps({"description": "草地", "mood": "温暖"})
    pages = [make_page(), make_page("spread")]

    content = understand_book(make_book(pages), FakeClient(reply))

    assert content.id == "chicken"
    assert content.title == "小鸡球球"
    assert content.source == "/tmp/chicken"
    assert content.page_count == 2
    assert content.failed_count == 0
    assert [p.description for p in content.pages] == ["草地", "草地"]


def test_book_keeps_going_after_a_failed_page():
    replies = [VisionError("boom"), json.dumps({"description": "草地"})]
    pages = [make_page(), make_page()]

    content = understand_book(make_book(pages), SequenceClient(replies))

    assert content.page_count == 2
    assert content.failed_count == 1
    assert content.pages[0].error == "boom"
    assert content.pages[1].description == "草地"


def test_book_with_no_pages():
    content = understand_book(make_book([]), FakeClient("{}"))

    assert content.page_count == 0
    assert content.failed_count == 0
