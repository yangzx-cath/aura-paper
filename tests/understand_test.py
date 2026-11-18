import json
from pathlib import Path

from aura_paper.book import Book, PageImage
from aura_paper.cache import Cache
from aura_paper.llm import LLMClient, LLMError
from aura_paper.understand import (
    BookContent,
    PageContent,
    save_book,
    understand_book,
    understand_page,
)


class FakeClient(LLMClient):
    def __init__(self, reply="", error=None):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.reply = reply
        self.error = error
        self.prompts = []

    def chat(
        self,
        prompt: str,
        *,
        image_path: Path | None = None,
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

    def chat(
        self,
        prompt: str,
        *,
        image_path: Path | None = None,
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
        path="page.jpg",
        kind=kind,
    )


def make_book(pages):
    return Book(
        id="chicken",
        title="小鸡球球",
        source="/tmp/chicken",
        pages=pages,
    )


def test_success():
    reply = json.dumps(
        {"page_text": "你好", "description": "草地", "mood": "温暖"}
    )

    content = understand_page(make_page(), FakeClient(reply))

    assert content.index == 3
    assert content.filename == "03.jpg"
    assert content.kind == "single"
    assert content.model == "fake-model"
    assert content.page_text == "你好"
    assert content.description == "草地"
    assert content.mood == "温暖"
    assert content.error == ""


def test_reads_the_page_role():
    reply = json.dumps({"role": "cover", "description": "封面"})

    content = understand_page(make_page(), FakeClient(reply))

    assert content.role == "cover"


def test_unknown_page_role_falls_back_to_story():
    reply = json.dumps({"role": "back", "description": "末页"})

    content = understand_page(make_page(), FakeClient(reply))

    assert content.role == "story"


def test_llm_error_is_recorded():
    client = FakeClient(error=LLMError("boom"))

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

    content = understand_page(make_page(kind="spread"), client)

    assert content.kind == "spread"
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
    replies = [LLMError("boom"), json.dumps({"description": "草地"})]
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


def test_story_pages_skip_cover_and_end():
    book = BookContent(
        id="demo",
        title="示例",
        source="/src",
        pages=[
            PageContent(index=0, filename="01.jpg", role="cover"),
            PageContent(index=1, filename="02.jpg"),
            PageContent(index=2, filename="03.jpg", role="end"),
        ],
    )

    assert [page.index for page in book.story_pages] == [1]


def test_story_pages_fall_back_to_every_page():
    book = BookContent(
        id="demo",
        title="示例",
        source="/src",
        pages=[
            PageContent(index=0, filename="01.jpg", role="cover"),
            PageContent(index=1, filename="02.jpg", role="end"),
        ],
    )

    assert [page.index for page in book.story_pages] == [0, 1]


def test_language_follows_the_printed_text():
    book = BookContent(
        id="demo",
        title="示例",
        source="/src",
        pages=[
            PageContent(index=0, filename="01.jpg", page_text="小鸡在走路"),
            PageContent(index=1, filename="02.jpg"),
        ],
    )

    assert book.language == "中文"


def test_an_english_book_reads_as_english():
    book = BookContent(
        id="demo",
        title="示例",
        source="/src",
        pages=[
            PageContent(index=0, filename="01.jpg", page_text="Kuan and I"),
            PageContent(index=1, filename="02.jpg"),
        ],
    )

    assert book.language == "英文"


NS = "understand/book"


def make_cached_page(tmp_path, data=b"image", index=3, name="03.jpg"):
    path = tmp_path / name
    path.write_bytes(data)
    return PageImage(index=index, filename=name, path=str(path))


def test_cache_stores_successful_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    client = FakeClient(json.dumps({"description": "草地"}))

    page = make_cached_page(tmp_path)
    understand_page(page, client, cache=cache, ns=NS)

    stored = list((tmp_path / "cache" / NS).glob("*.json"))
    assert len(stored) == 1
    assert cache.stats() == {"hit": 0, "miss": 1}


def test_cache_reuses_stored_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    first = FakeClient(json.dumps({"description": "草地"}))
    understand_page(page, first, cache=cache, ns=NS)

    second = FakeClient(json.dumps({"description": "更动"}))
    content = understand_page(page, second, cache=cache, ns=NS)

    assert content.description == "草地"
    assert second.prompts == []
    assert cache.stats() == {"hit": 1, "miss": 1}


def test_cache_does_not_store_failed_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    client = FakeClient(error=LLMError("boom"))

    understand_page(make_cached_page(tmp_path), client, cache=cache, ns=NS)

    assert not (tmp_path / "cache" / NS).exists()


def test_failed_page_is_retried(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    failing = FakeClient(error=LLMError("boom"))
    understand_page(page, failing, cache=cache, ns=NS)

    client = FakeClient(json.dumps({"description": "草地"}))
    content = understand_page(page, client, cache=cache, ns=NS)

    assert content.description == "草地"
    assert len(client.prompts) == 1


def test_changed_image_is_a_miss(tmp_path):
    cache = Cache(tmp_path / "cache")
    first = FakeClient(json.dumps({"description": "一"}))
    page = make_cached_page(tmp_path, data=b"one")
    understand_page(page, first, cache=cache, ns=NS)

    second = FakeClient(json.dumps({"description": "二"}))
    page = make_cached_page(tmp_path, data=b"two")
    content = understand_page(page, second, cache=cache, ns=NS)

    assert content.description == "二"
    assert len(second.prompts) == 1


def test_cached_page_takes_filename_from_current_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    understand_page(
        page,
        FakeClient(json.dumps({"description": "草地"})),
        cache=cache,
        ns=NS,
    )

    renamed = PageImage(index=3, filename="renamed.jpg", path=page.path)
    content = understand_page(renamed, FakeClient(), cache=cache, ns=NS)

    assert content.filename == "renamed.jpg"
    assert content.description == "草地"


def test_cache_keeps_every_page_field(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    reply = json.dumps(
        {
            "role": "cover",
            "page_text": "小蝴蝶，你好。",
            "footer": "定价：38.00 元",
            "description": "封面",
            "mood": "温暖",
            "mood_detail": "有一点期待",
        }
    )
    understand_page(page, FakeClient(reply), cache=cache, ns=NS)

    content = understand_page(page, FakeClient(), cache=cache, ns=NS)

    assert content.role == "cover"
    assert content.page_text == "小蝴蝶，你好。"
    assert content.footer == "定价：38.00 元"
    assert content.description == "封面"
    assert content.mood == "温暖"
    assert content.mood_detail == "有一点期待"


def make_cached_book(tmp_path, count=3):
    pages = []
    for index in range(count):
        name = f"{index:02d}.jpg"
        data = f"p{index}".encode()
        page = make_cached_page(tmp_path, data=data, index=index, name=name)
        pages.append(page)
    return make_book(pages)


def test_book_caches_each_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    book = make_cached_book(tmp_path)
    client = FakeClient(json.dumps({"description": "草地"}))

    understand_book(book, client, cache=cache, workers=3)

    root = tmp_path / "cache" / "understand" / book.id
    assert len(list(root.glob("*.json"))) == 3
    assert cache.stats() == {"hit": 0, "miss": 3}


def test_second_book_run_hits_every_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    book = make_cached_book(tmp_path)
    first = FakeClient(json.dumps({"description": "草地"}))
    understand_book(book, first, cache=cache)

    second = FakeClient(json.dumps({"description": "更动"}))
    content = understand_book(book, second, cache=cache)

    assert second.prompts == []
    assert [p.description for p in content.pages] == ["草地"] * 3
    assert cache.stats() == {"hit": 3, "miss": 3}


def test_only_the_failed_page_is_retried(tmp_path):
    cache = Cache(tmp_path / "cache")
    book = make_cached_book(tmp_path)
    replies = [
        LLMError("boom"),
        json.dumps({"description": "二"}),
        json.dumps({"description": "三"}),
    ]
    understand_book(book, SequenceClient(replies), cache=cache)

    retry = SequenceClient([json.dumps({"description": "重试"})])
    content = understand_book(book, retry, cache=cache)

    assert len(retry.prompts) == 1
    assert [p.description for p in content.pages] == ["重试", "二", "三"]
    assert content.failed_count == 0


def test_namespaces_are_isolated_per_book(tmp_path):
    cache = Cache(tmp_path / "cache")
    first = make_cached_book(tmp_path)
    client = FakeClient(json.dumps({"description": "一"}))
    understand_book(first, client, cache=cache)

    other = Book(id="other", pages=first.pages)
    second = FakeClient(json.dumps({"description": "二"}))
    content = understand_book(other, second, cache=cache)

    assert len(second.prompts) == 3
    assert [p.description for p in content.pages] == ["二"] * 3


def test_disabled_cache_calls_the_model_every_time(tmp_path):
    cache = Cache(tmp_path / "cache", enabled=False)
    page = make_cached_page(tmp_path)
    client = FakeClient(json.dumps({"description": "草地"}))

    understand_page(page, client, cache=cache, ns=NS)
    understand_page(page, client, cache=cache, ns=NS)

    assert len(client.prompts) == 2
    assert not (tmp_path / "cache").exists()


def test_save_book_writes_book_json(tmp_path):
    book = BookContent(id="demo", title="示例", source="/src")

    path = save_book(book, tmp_path)

    assert path == tmp_path / "demo" / "book.json"
    assert path.is_file()


def test_save_book_writes_the_page_fields(tmp_path):
    page = PageContent(index=2, filename="03.jpg", description="草地")
    book = BookContent(id="demo", title="示例", source="/src")
    book.pages.append(page)

    path = save_book(book, tmp_path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["page_count"] == 1
    assert data["pages"][0]["description"] == "草地"
    assert data["pages"][0]["kind"] == "single"


def test_book_dict_round_trip():
    page = PageContent(
        index=1,
        filename="02.jpg",
        kind="spread",
        role="cover",
        page_text="文字",
        footer="定价：38.00 元",
        description="草地",
        mood="温暖",
        model="m",
    )
    book = BookContent(id="demo", title="示例", source="/src")
    book.pages.append(page)

    assert BookContent.from_dict(book.to_dict()) == book
