import json
from pathlib import Path

from PIL import Image

from aura_paper.schema.content import BookContent, PageContent, Panel
from aura_paper.stages.crop import crop
from aura_paper.store.output import write_json


# Write an understand record and the page images it points at.
def make_book(root: Path, pages: list[PageContent]) -> None:
    pages_dir = root / "demo" / "pages"
    pages_dir.mkdir(parents=True)
    for page in pages:
        image = Image.new("RGB", (200, 100), "white")
        image.save(pages_dir / page.filename)
    content = BookContent(id="demo", source=str(pages_dir), pages=pages)
    write_json("demo", "understand", content.to_dict(), root)


def test_cuts_one_file_per_panel(tmp_path):
    page = PageContent(
        index=0,
        filename="p000.jpg",
        width=200,
        height=100,
        panels=[
            Panel(index=0, box=[0, 0, 500, 1000]),
            Panel(index=1, box=[500, 0, 1000, 1000]),
        ],
    )
    make_book(tmp_path, [page])

    result = crop("demo", root=tmp_path)

    assert result.error == ""
    assert [panel.file for panel in result.panels] == [
        "p000_0.jpg",
        "p000_1.jpg",
    ]
    assert (tmp_path / "demo" / "panels" / "p000_1.jpg").is_file()
    saved = json.loads(
        (tmp_path / "demo" / "crop.json").read_text(encoding="utf-8")
    )
    assert saved["id"] == "demo"
    assert saved["panels"][0]["box"] == [0, 0, 500, 1000]
    assert "generated_at" in saved


def test_reports_a_book_without_panels(tmp_path):
    page = PageContent(index=0, filename="p000.jpg", width=200, height=100)
    make_book(tmp_path, [page])

    result = crop("demo", root=tmp_path)

    assert result.panels == []
    assert result.error == "understand.json holds no panel box"
