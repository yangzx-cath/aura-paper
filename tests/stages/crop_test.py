import json
from pathlib import Path

from PIL import Image

from aura_paper.schema.content import BookContent, Figure, PageContent, Panel
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


# Describe one figure with a per-mille box.
def figure(box, facing="正面", view="全身", occlusion="无") -> Figure:
    return Figure(
        name="小满",
        body="小女孩",
        outfit="粉色上衣",
        view=view,
        facing=facing,
        occlusion=occlusion,
        box=box,
    )


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


def test_keeps_only_figures_that_can_stand_alone(tmp_path):
    pages = [
        PageContent(
            index=0,
            filename="p000.jpg",
            width=200,
            height=100,
            figures=[
                figure([0, 0, 200, 250]),
                figure([500, 0, 699, 251]),
                figure([0, 400, 300, 700], view="半身"),
                figure([400, 400, 700, 700], facing="背面"),
                figure([700, 400, 1000, 700], occlusion="遮挡"),
                figure([0, 0, 0, 0]),
            ],
        ),
        PageContent(
            index=1,
            filename="p001.jpg",
            width=200,
            height=100,
            figures=[
                figure([0, 0, 100, 1000]),
                figure([69, 0, 169, 1000]),
                figure([400, 0, 600, 1000]),
            ],
        ),
        PageContent(
            index=2,
            filename="p002.jpg",
            width=200,
            height=100,
            figures=[
                figure([0, 0, 100, 1000]),
                figure([70, 0, 170, 1000]),
            ],
        ),
    ]
    make_book(tmp_path, pages)

    result = crop("demo", root=tmp_path)

    assert sorted(item.file for item in result.figures) == [
        "p000_f0.jpg",
        "p001_f2.jpg",
        "p002_f0.jpg",
        "p002_f1.jpg",
    ]


def test_puts_a_face_before_a_side_view(tmp_path):
    page = PageContent(
        index=0,
        filename="p000.jpg",
        width=200,
        height=100,
        figures=[
            figure([0, 0, 300, 400], facing="侧面"),
            figure([400, 0, 700, 400], facing="正面"),
        ],
    )
    make_book(tmp_path, [page])

    result = crop("demo", root=tmp_path)

    assert [item.file for item in result.figures] == [
        "p000_f1.jpg",
        "p000_f0.jpg",
    ]
