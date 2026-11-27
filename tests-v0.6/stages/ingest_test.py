import json

from aura_paper.clients.llm import LLMClient
from aura_paper.stages.ingest import ingest
from PIL import Image


class FakeLLM(LLMClient):
    def __init__(self, two_pages):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.two_pages = two_pages
        self.calls = 0

    def chat(self, prompt, *, images=None, json_mode=True):
        self.calls += 1
        return json.dumps({"two_pages": self.two_pages, "reason": ""})


# Pillow writes one point per pixel, so dpi=72 keeps the sizes exact.
def make_pdf(path, sizes):
    images = []
    for size in sizes:
        images.append(Image.new("RGB", size, "white"))
    images[0].save(path, "PDF", save_all=True, append_images=images[1:])
    return path


def test_splits_a_wide_page_into_two(tmp_path):
    pdf = make_pdf(tmp_path / "book.pdf", [(200, 200), (400, 200)])
    llm = FakeLLM(two_pages=True)

    book = ingest(pdf, "demo", llm=llm, root=tmp_path, dpi=72)

    assert [(page.width, page.height) for page in book.pages] == [
        (200, 200),
        (200, 200),
        (200, 200),
    ]
    assert [page.origin for page in book.pages] == ["page", "half", "half"]
    assert llm.calls == 1
    assert (tmp_path / "demo" / "ingest.json").is_file()


def test_stitches_adjacent_pages_of_one_spread(tmp_path):
    pdf = make_pdf(
        tmp_path / "book.pdf",
        [(200, 300), (200, 300), (200, 300)],
    )
    llm = FakeLLM(two_pages=False)

    book = ingest(pdf, "demo", llm=llm, root=tmp_path, dpi=72)

    assert [(page.width, page.height) for page in book.pages] == [
        (200, 300),
        (400, 300),
    ]
    assert book.pages[1].sources == [1, 2]
    assert book.pages[1].origin == "spread"
    assert llm.calls == 0
