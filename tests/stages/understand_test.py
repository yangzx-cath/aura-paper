import json
from pathlib import Path

from PIL import Image

from aura_paper.clients.llm import LLMClient
from aura_paper.output import write_json
from aura_paper.schema.book import Book, Page
from aura_paper.stages.understand import understand

REPLY = json.dumps(
    {
        "title": "测试绘本",
        "author": "作者",
        "illustrator": "",
        "description": "封面",
        "meta_text": "阅读指导",
        "light": "白天，阳光明媚",
        "panels": [
            {
                "box": [0, 0, 400, 500],
                "text": "三块、",
                "description": "小女孩坐在地上搭积木",
            }
        ],
        "figures": [
            {
                "name": "小满",
                "body": "小女孩",
                "outfit": "粉色上衣",
                "view": "全身",
                "facing": "正面",
                "occlusion": "无",
                "box": [10, 20, 40, 60],
                "panel": 0,
            }
        ],
        "uncertain": [],
    }
)


class FakeLLM(LLMClient):
    def __init__(self):
        super().__init__("http://example/v1", "test-key", "fake-model")
        self.calls = 0

    def chat(self, prompt, *, image_path=None, json_mode=True):
        self.calls += 1
        return REPLY


# Write an ingest record and the two page images it points at.
def make_book(root: Path) -> None:
    pages_dir = root / "demo" / "pages"
    pages_dir.mkdir(parents=True)
    Image.new("RGB", (100, 80), "white").save(pages_dir / "p000.jpg")
    Image.new("RGB", (100, 120), "white").save(pages_dir / "p001.jpg")
    book = Book(
        id="demo",
        source="demo.pdf",
        source_count=2,
        pages=[
            Page(index=0, filename="p000.jpg", width=100, height=80),
            Page(index=1, filename="p001.jpg", width=100, height=120),
        ],
    )
    write_json("demo", "ingest", book.to_dict(), root)


def test_reads_the_cover_and_one_page(tmp_path):
    make_book(tmp_path)
    llm = FakeLLM()

    content = understand("demo", llm=llm, root=tmp_path)

    assert content.page_count == 2
    assert content.title == "测试绘本"
    assert content.failed_count == 0
    assert content.pages[0].width == 100
    assert content.pages[0].height == 80
    assert content.pages[1].meta_text == "阅读指导"
    assert content.pages[1].page_text == "三块、"
    assert content.pages[1].light == "白天，阳光明媚"
    assert content.pages[1].width == 100
    assert content.pages[1].height == 120
    assert content.pages[1].panels[0].box == [0, 0, 400, 500]
    assert content.pages[1].panels[0].text == "三块、"
    assert content.pages[1].panels[0].description == "小女孩坐在地上搭积木"
    assert content.pages[1].panels[0].needs_scene is True
    assert content.pages[1].figures[0].panel == 0
    assert llm.calls == 2
    assert (tmp_path / "demo" / "understand.json").is_file()
    assert (tmp_path / "demo" / "panels" / "p001_0.jpg").is_file()
