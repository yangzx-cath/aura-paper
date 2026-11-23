import json

from PIL import Image

from aura_paper.cache import Cache
from aura_paper.clients.llm import LLMClient
from aura_paper.output import write_json
from aura_paper.schema.cast import BookCast
from aura_paper.schema.content import BookContent
from aura_paper.stages.identify import identify


# Answer every page with the same panels.
class FakeLLM(LLMClient):
    def __init__(self, panels):
        super().__init__("http://example/v1", "key", "fake-model")
        self.panels = panels
        self.calls = 0

    def chat(self, prompt, *, images=None, json_mode=True, max_tokens=0):
        self.calls += 1
        return json.dumps({"panels": self.panels})


# One figure of a page: a whole child unless told otherwise.
def figure(view="全身", occlusion="无", box=(500, 100, 900, 900)):
    return {
        "index": 0,
        "name": "",
        "body": "孩子",
        "outfit": "粉衣",
        "view": view,
        "facing": "斜侧",
        "occlusion": occlusion,
        "box": list(box) if box else None,
    }


# One page with a single figure and the given panels.
def page(filename, one_figure, panels=(0,)):
    return {
        "filename": filename,
        "page_text": "三块、四块。",
        "panels": [
            {"index": index, "box": [0, 0, 1000, 300], "needs_scene": True}
            for index in panels
        ],
        "figures": [one_figure],
    }


# Write the understand and cast artifacts the stage reads, plus the images.
def make_book(root, pages, cast=None):
    book = root / "demo"
    panels = book / "panels"
    figures = book / "figures"
    panels.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    for item in pages:
        for panel in item["panels"]:
            name = (
                f"{item['filename'].replace('.jpg', '')}_{panel['index']}.jpg"
            )
            Image.new("RGB", (600, 400)).save(panels / name)
    Image.new("RGB", (300, 400)).save(figures / "p002_f0.jpg")

    content = BookContent.from_dict({"id": "demo", "pages": pages})
    write_json("demo", "understand", content.to_dict(), root)
    members = cast or [
        {
            "id": "c1",
            "name": "小满",
            "look": "橙背带裤",
            "pictures": ["p002_f0.jpg"],
        }
    ]
    write_json(
        "demo", "cast", BookCast.from_dict({"cast": members}).to_dict(), root
    )


def test_reads_only_the_pages_with_a_partly_shown_figure(tmp_path):
    make_book(
        tmp_path,
        [
            page("p002.jpg", figure(view="半身")),
            page("p003.jpg", figure()),
        ],
    )
    llm = FakeLLM(
        [{"panel": 0, "people": [{"cast": "c1", "parts": "衣服和腿"}]}]
    )

    result = identify("demo", llm=llm, root=tmp_path)

    assert llm.calls == 1
    assert [panel.page for panel in result.panels] == ["p002.jpg"]
    assert result.panels[0].people[0].parts == "衣服和腿"
    assert result.error == ""


def test_drops_a_person_whose_cast_id_does_not_exist(tmp_path):
    make_book(tmp_path, [page("p002.jpg", figure(view="半身"))])
    llm = FakeLLM(
        [
            {
                "panel": 0,
                "people": [
                    {"cast": "c1", "parts": "全身"},
                    {"cast": "c9", "parts": "头"},
                ],
            }
        ]
    )

    result = identify("demo", llm=llm, root=tmp_path)

    assert [person.cast for person in result.panels[0].people] == ["c1"]


def test_drops_a_panel_that_is_not_on_the_page(tmp_path):
    make_book(tmp_path, [page("p002.jpg", figure(view="半身"), panels=(0, 1))])
    llm = FakeLLM(
        [
            {"panel": 0, "people": [{"cast": "c1", "parts": "全身"}]},
            {"panel": 7, "people": [{"cast": "c1", "parts": "头"}]},
        ]
    )

    result = identify("demo", llm=llm, root=tmp_path)

    assert [panel.panel for panel in result.panels] == [0]


def test_reads_one_page_only(tmp_path):
    make_book(
        tmp_path,
        [
            page("p002.jpg", figure(view="半身")),
            page("p003.jpg", figure(occlusion="部分")),
        ],
    )
    llm = FakeLLM([{"panel": 0, "people": []}])

    result = identify("demo", llm=llm, only="p003", root=tmp_path)

    assert llm.calls == 1
    assert [panel.page for panel in result.panels] == ["p003.jpg"]


def test_reuses_the_cached_answer(tmp_path):
    make_book(tmp_path, [page("p002.jpg", figure(view="半身"))])
    llm = FakeLLM([{"panel": 0, "people": [{"cast": "c1", "parts": "全身"}]}])
    cache = Cache(tmp_path / "cache")

    identify("demo", llm=llm, root=tmp_path, cache=cache)
    identify("demo", llm=llm, root=tmp_path, cache=Cache(tmp_path / "cache"))

    assert llm.calls == 1
