import json
from pathlib import Path

from aura_paper.book import Book, Page
from aura_paper.cache import Cache
from aura_paper.llm import LLMClient, LLMError
from aura_paper.understand import (
    BookContent,
    CoverContent,
    Figure,
    PageContent,
    save_content,
    understand_book,
    understand_cover,
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


def make_page(kind="portrait"):
    width, height = (1700, 1200) if kind == "landscape" else (1200, 1700)
    return Page(index=3, filename="03.jpg", width=width, height=height)


def make_book(pages, directory="/tmp/chicken"):
    return Book(
        id="chicken",
        source="/tmp/chicken.pdf",
        directory=directory,
        pages=pages,
    )


def test_reads_the_cover():
    reply = json.dumps(
        {
            "title": "小蝴蝶",
            "author": "张三",
            "illustrator": "李四",
            "description": "封面上有一只蝴蝶",
        }
    )

    content, cover = understand_cover(make_page(), FakeClient(reply))

    assert cover.title == "小蝴蝶"
    assert cover.author == "张三"
    assert cover.illustrator == "李四"
    assert content.error == ""
    assert content.description == "封面上有一只蝴蝶"


def test_cover_uses_the_cover_prompt():
    client = FakeClient(json.dumps({"title": "小蝴蝶"}))

    understand_cover(make_page(), client)

    assert "封面" in client.prompts[0]
    assert "page_text" not in client.prompts[0]


def test_a_cover_without_a_title_is_an_error():
    content, cover = understand_cover(make_page(), FakeClient("{}"))

    assert cover.title == ""
    assert content.error == "model returned no content"


def test_success():
    reply = json.dumps({"page_text": "你好", "description": "草地"})

    content = understand_page(make_page(), FakeClient(reply))

    assert content.index == 3
    assert content.filename == "03.jpg"
    assert content.kind == "portrait"
    assert content.model == "fake-model"
    assert content.page_text == "你好"
    assert content.description == "草地"
    assert content.error == ""


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


def test_uncertain_copes_with_a_malformed_reply():
    not_a_list = json.dumps(
        {"description": "草地", "uncertain": "红衣孩子身份不明"}
    )
    with_junk = json.dumps(
        {
            "description": "草地",
            "uncertain": [{"x": 1}, [], "  ", "说话人未标明"],
        }
    )

    assert understand_page(make_page(), FakeClient(not_a_list)).uncertain == []
    assert understand_page(make_page(), FakeClient(with_junk)).uncertain == [
        "说话人未标明"
    ]


def test_figures_cope_with_a_malformed_reply():
    not_a_list = json.dumps({"description": "草地", "figures": "一个女孩"})
    with_junk = json.dumps(
        {
            "description": "草地",
            "figures": [None, [], "女孩", {"body": "粉衣"}],
        }
    )

    assert understand_page(make_page(), FakeClient(not_a_list)).figures == []
    kept = understand_page(make_page(), FakeClient(with_junk)).figures
    assert [figure.body for figure in kept] == ["粉衣"]


def test_a_bad_box_is_dropped():
    good = Figure.from_dict({"box": [0.1, 0.2, 0.5, 0.9]})
    clamped = Figure.from_dict({"box": [-0.5, 0.2, 1.5, 0.9]})
    inverted = Figure.from_dict({"box": [0.5, 0.2, 0.1, 0.9]})

    assert good.box == [0.1, 0.2, 0.5, 0.9]
    assert clamped.box == [0.0, 0.2, 1.0, 0.9]
    assert Figure.from_dict({"box": [0.1, 0.2, 0.5]}).box is None
    assert Figure.from_dict({"box": "左下角"}).box is None
    assert inverted.box is None


def test_empty_payload_is_an_error():
    content = understand_page(make_page(), FakeClient("{}"))

    assert content.error == "model returned no content"


def test_book_collects_every_page():
    reply = json.dumps({"title": "小鸡球球", "description": "草地"})
    pages = [make_page(), make_page("landscape")]

    content = understand_book(make_book(pages), FakeClient(reply))

    assert content.id == "chicken"
    assert content.title == "小鸡球球"
    assert content.source == "/tmp/chicken"
    assert content.page_count == 2
    assert content.failed_count == 0
    assert [p.description for p in content.pages] == ["草地", "草地"]


def test_a_failed_cover_counts_as_a_failure():
    replies = [LLMError("boom"), json.dumps({"description": "草地"})]
    pages = [make_page(), make_page()]

    content = understand_book(make_book(pages), SequenceClient(replies))

    assert content.failed_count == 1
    assert content.pages[1].description == "草地"

    cover = content.cover_page
    assert cover is not None
    assert cover.error == "boom"


def test_book_keeps_going_after_a_failed_page():
    replies = [
        json.dumps({"title": "小蝴蝶"}),
        LLMError("boom"),
        json.dumps({"description": "草地"}),
    ]
    pages = [make_page(), make_page(), make_page()]

    content = understand_book(make_book(pages), SequenceClient(replies))

    assert content.page_count == 3
    assert content.failed_count == 1
    assert content.pages[1].error == "boom"
    assert content.pages[2].description == "草地"


def test_book_with_no_pages():
    content = understand_book(make_book([]), FakeClient("{}"))

    assert content.page_count == 0
    assert content.failed_count == 0
    assert content.cover_page is None


def test_story_pages_skip_the_cover():
    book = BookContent(
        id="demo",
        source="/src",
        cover=CoverContent(title="小蝴蝶"),
        pages=[
            PageContent(index=0, filename="01.jpg"),
            PageContent(index=1, filename="02.jpg"),
            PageContent(index=2, filename="03.jpg"),
        ],
    )

    assert [page.index for page in book.story_pages] == [1, 2]


def test_story_pages_of_a_single_page_book():
    book = BookContent(
        id="demo",
        source="/src",
        pages=[PageContent(index=0, filename="01.jpg")],
    )

    assert book.story_pages == []


def test_language_follows_the_printed_text():
    book = BookContent(
        id="demo",
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
    return Page(index=index, filename=name, width=1200, height=1700)


# Read one page through the cache, with its image in tmp_path.
def read_page(page, client, cache, tmp_path):
    return understand_page(
        page,
        client,
        cache=cache,
        ns=NS,
        directory=str(tmp_path),
    )


def test_cache_stores_successful_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    client = FakeClient(json.dumps({"description": "草地"}))

    page = make_cached_page(tmp_path)
    read_page(page, client, cache, tmp_path)

    stored = list((tmp_path / "cache" / NS).glob("*.json"))
    assert len(stored) == 1
    assert cache.stats() == {"hit": 0, "miss": 1}


def test_cache_reuses_stored_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    first = FakeClient(json.dumps({"description": "草地"}))
    read_page(page, first, cache, tmp_path)

    second = FakeClient(json.dumps({"description": "更动"}))
    content = read_page(page, second, cache, tmp_path)

    assert content.description == "草地"
    assert second.prompts == []
    assert cache.stats() == {"hit": 1, "miss": 1}


def test_a_client_with_another_effort_is_a_cache_miss(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    quick = FakeClient(json.dumps({"description": "草地"}))
    quick.reasoning_effort = "low"
    read_page(page, quick, cache, tmp_path)

    full = FakeClient(json.dumps({"description": "更动"}))
    content = read_page(page, full, cache, tmp_path)

    assert content.description == "更动"
    assert len(full.prompts) == 1


def test_cache_does_not_store_failed_page(tmp_path):
    cache = Cache(tmp_path / "cache")
    client = FakeClient(error=LLMError("boom"))

    understand_page(
        make_cached_page(tmp_path),
        client,
        cache=cache,
        ns=NS,
        directory=str(tmp_path),
    )

    assert not (tmp_path / "cache" / NS).exists()


def test_failed_page_is_retried(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    failing = FakeClient(error=LLMError("boom"))
    read_page(page, failing, cache, tmp_path)

    client = FakeClient(json.dumps({"description": "草地"}))
    content = read_page(page, client, cache, tmp_path)

    assert content.description == "草地"
    assert len(client.prompts) == 1


def test_changed_image_is_a_miss(tmp_path):
    cache = Cache(tmp_path / "cache")
    first = FakeClient(json.dumps({"description": "一"}))
    page = make_cached_page(tmp_path, data=b"one")
    read_page(page, first, cache, tmp_path)

    second = FakeClient(json.dumps({"description": "二"}))
    page = make_cached_page(tmp_path, data=b"two")
    content = read_page(page, second, cache, tmp_path)

    assert content.description == "二"
    assert len(second.prompts) == 1


def test_cache_keeps_every_page_field(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_cached_page(tmp_path)
    reply = json.dumps(
        {
            "page_text": "小蝴蝶，你好。",
            "footer": "定价：38.00 元",
            "description": "封面",
            "figures": [
                {
                    "name": "花花",
                    "species": "人类",
                    "body": "粉色蝴蝶结，丸子头，浅肤色",
                    "outfit": "粉条纹短裤",
                    "view": "全身",
                    "facing": "正面",
                    "occlusion": "无",
                    "box": [0.1, 0.2, 0.5, 0.9],
                }
            ],
            "uncertain": ["红衣孩子身份不明"],
        }
    )
    read_page(page, FakeClient(reply), cache, tmp_path)

    content = read_page(page, FakeClient(), cache, tmp_path)

    assert content.page_text == "小蝴蝶，你好。"
    assert content.footer == "定价：38.00 元"
    assert content.description == "封面"
    assert content.figures[0].name == "花花"
    assert content.figures[0].species == "人类"
    assert content.figures[0].outfit == "粉条纹短裤"
    assert content.figures[0].view == "全身"
    assert content.figures[0].box == [0.1, 0.2, 0.5, 0.9]
    assert content.uncertain == ["红衣孩子身份不明"]


def make_cached_book(tmp_path, count=3):
    pages = []
    for index in range(count):
        name = f"{index:02d}.jpg"
        data = f"p{index}".encode()
        page = make_cached_page(tmp_path, data=data, index=index, name=name)
        pages.append(page)
    return make_book(pages, directory=str(tmp_path))


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

    other = Book(id="other", directory=str(tmp_path), pages=first.pages)
    second = FakeClient(json.dumps({"description": "二"}))
    content = understand_book(other, second, cache=cache)

    assert len(second.prompts) == 3
    assert [p.description for p in content.pages] == ["二"] * 3


def test_disabled_cache_calls_the_model_every_time(tmp_path):
    cache = Cache(tmp_path / "cache", enabled=False)
    page = make_cached_page(tmp_path)
    client = FakeClient(json.dumps({"description": "草地"}))

    read_page(page, client, cache, tmp_path)
    read_page(page, client, cache, tmp_path)

    assert len(client.prompts) == 2
    assert not (tmp_path / "cache").exists()


def test_save_content_writes_content_json(tmp_path):
    book = BookContent(id="demo", source="/src")

    path = save_content(book, tmp_path)

    assert path == tmp_path / "demo" / "content.json"
    assert path.is_file()


def test_save_content_writes_the_page_fields(tmp_path):
    page = PageContent(index=2, filename="03.jpg", description="草地")
    book = BookContent(id="demo", source="/src")
    book.pages.append(page)

    path = save_content(book, tmp_path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["page_count"] == 1
    assert data["pages"][0]["description"] == "草地"
    assert data["pages"][0]["kind"] == "portrait"


def test_book_dict_round_trip():
    page = PageContent(
        index=1,
        filename="02.jpg",
        kind="landscape",
        page_text="文字",
        footer="定价：38.00 元",
        description="草地",
        model="m",
    )
    book = BookContent(
        id="demo",
        source="/src",
        cover=CoverContent(title="小蝴蝶", author="张三"),
        pages=[page],
    )

    assert BookContent.from_dict(book.to_dict()) == book


def test_figures_are_numbered_by_position():
    reply = json.dumps(
        {
            "page_text": "你好",
            "description": "草地",
            "figures": [
                {"name": "花花", "box": [0.1, 0.1, 0.2, 0.2]},
                {"name": "小满", "box": [0.3, 0.1, 0.4, 0.2]},
            ],
        }
    )

    content = understand_page(make_page(), FakeClient(reply))

    assert [figure.index for figure in content.figures] == [0, 1]
