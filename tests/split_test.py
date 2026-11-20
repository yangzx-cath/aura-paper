import json

from PIL import Image

from aura_paper.book import Book, Page
from aura_paper.cache import Cache
from aura_paper.llm import LLMClient, LLMError
from aura_paper.split import detect_layout, save_split, split_book

# The folder the cut pages land in, kept apart from the source images.
TARGET = "split"


class FakeClient(LLMClient):
    def __init__(self, reply="", error=None):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.reply = reply
        self.error = error
        self.prompts = []
        self.sizes = []

    def chat(
        self,
        prompt: str,
        *,
        image_path=None,
        json_mode: bool = True,
    ) -> str:
        self.prompts.append(prompt)
        if image_path is not None:
            with Image.open(image_path) as image:
                self.sizes.append(image.size)
        if self.error:
            raise self.error
        return self.reply


def make_page(tmp_path, size=(1600, 800), index=1, name="01.jpg"):
    Image.new("RGB", size, "white").save(tmp_path / name)
    return Page(
        index=index,
        filename=name,
        width=size[0],
        height=size[1],
    )


def make_book(pages, folder):
    return Book(
        id="chicken",
        source="/tmp/chicken.pdf",
        directory=str(folder),
        pages=pages,
    )


def test_a_portrait_page_is_never_asked(tmp_path):
    client = FakeClient("{}")
    page = make_page(tmp_path, size=(800, 1000))

    layout = detect_layout(page, client, directory=str(tmp_path))

    assert layout.two_pages is False
    assert client.prompts == []


def test_a_two_page_image_asks_the_model(tmp_path):
    client = FakeClient(
        json.dumps({"two_pages": True, "reason": "两半各自成页"})
    )
    page = make_page(tmp_path)

    layout = detect_layout(page, client, directory=str(tmp_path))

    assert layout.two_pages is True
    assert layout.reason == "两半各自成页"
    assert "two_pages" in client.prompts[0]


def test_the_model_gets_a_small_copy(tmp_path):
    client = FakeClient(json.dumps({"two_pages": True}))
    page = make_page(tmp_path, size=(3600, 1800))

    detect_layout(page, client, directory=str(tmp_path))

    assert client.sizes == [(1024, 512)]


def test_a_string_answer_is_read_as_a_bool(tmp_path):
    client = FakeClient(json.dumps({"two_pages": "false"}))
    page = make_page(tmp_path)

    layout = detect_layout(page, client, directory=str(tmp_path))

    assert layout.two_pages is False


def test_a_failed_page_is_kept_whole(tmp_path):
    client = FakeClient(error=LLMError("boom"))
    book = make_book([make_page(tmp_path, name="00.jpg")], tmp_path)

    split = split_book(book, client, target=tmp_path / TARGET)

    assert split.failed_count == 1
    assert [page.filename for page in split.book.pages] == ["00.jpg"]


def test_two_pages_become_two_images(tmp_path):
    client = FakeClient(json.dumps({"two_pages": True}))
    pages = [
        make_page(tmp_path, size=(800, 800), index=0, name="00.jpg"),
        make_page(tmp_path, size=(1600, 800), index=1, name="01.jpg"),
    ]

    split = split_book(
        make_book(pages, tmp_path), client, target=tmp_path / TARGET
    )

    assert split.two_page_count == 1
    assert [page.filename for page in split.book.pages] == [
        "00.jpg",
        "01a.jpg",
        "01b.jpg",
    ]
    assert [page.index for page in split.book.pages] == [0, 1, 2]
    assert [page.width for page in split.book.pages] == [800, 800, 800]


def test_the_cut_follows_the_middle_of_the_image(tmp_path):
    path = tmp_path / "01.jpg"
    image = Image.new("RGB", (1600, 800), "red")
    image.paste("blue", (800, 0, 1600, 800))
    image.save(path)
    page = Page(index=0, filename="01.jpg", width=1600, height=800)
    client = FakeClient(json.dumps({"two_pages": True}))

    split_book(make_book([page], tmp_path), client, target=tmp_path / TARGET)

    with Image.open(tmp_path / TARGET / "01a.jpg") as left:
        pixel = left.getpixel((10, 10))
        assert isinstance(pixel, tuple) and pixel[0] > 200
    with Image.open(tmp_path / TARGET / "01b.jpg") as right:
        pixel = right.getpixel((10, 10))
        assert isinstance(pixel, tuple) and pixel[2] > 200


def test_second_run_hits_the_cache(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_page(tmp_path, size=(1600, 800))
    book = make_book([page], tmp_path)
    first = FakeClient(json.dumps({"two_pages": True}))
    split_book(book, first, target=tmp_path / TARGET, cache=cache)

    second = FakeClient("")
    split_book(book, second, target=tmp_path / TARGET, cache=cache)

    assert second.prompts == []
    assert cache.stats() == {"hit": 1, "miss": 1}


def test_a_failed_page_is_not_cached(tmp_path):
    cache = Cache(tmp_path / "cache")
    page = make_page(tmp_path, size=(1600, 800))

    detect_layout(
        page,
        FakeClient(error=LLMError("boom")),
        cache=cache,
        directory=str(tmp_path),
    )

    assert not (tmp_path / "cache" / "split").exists()


def test_save_split_writes_pages_json(tmp_path):
    split = split_book(
        make_book([make_page(tmp_path, size=(800, 800))], tmp_path),
        FakeClient("{}"),
        target=tmp_path / TARGET,
    )

    path = save_split(split, tmp_path)

    assert path == tmp_path / "chicken" / "pages.json"
    assert path.is_file()


# A page judged single again must not leave its old halves behind.
def test_old_halves_are_cleared_on_the_next_run(tmp_path):
    page = make_page(tmp_path, size=(1600, 800))
    book = make_book([page], tmp_path)
    split_book(
        book,
        FakeClient(json.dumps({"two_pages": True})),
        target=tmp_path / TARGET,
    )

    split_book(
        book,
        FakeClient(json.dumps({"two_pages": False})),
        target=tmp_path / TARGET,
    )

    assert sorted(p.name for p in (tmp_path / TARGET).iterdir()) == ["01.jpg"]
