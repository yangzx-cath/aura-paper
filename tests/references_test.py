from pathlib import Path

from PIL import Image

from aura_paper.references import save_references
from aura_paper.story import Reference, Story
from aura_paper.understand import BookContent, Figure, PageContent

SIDE = 1200


def make_page(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "page_001.jpg"
    Image.new("RGB", (SIDE, SIDE), "white").save(path)
    return path


def make_content(box: list[int] | None) -> BookContent:
    page = PageContent(
        index=1,
        filename="page_001.jpg",
        figures=[Figure(index=0, name="花花", box=box)],
    )
    return BookContent(id="demo", source="/src", pages=[page])


def make_story() -> Story:
    return Story(
        id="demo",
        characters=["花花"],
        references=[Reference("花花", 1, 0, "全身正面")],
    )


def test_crop_is_written_under_the_references_folder(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    written = save_references(
        make_content([25, 25, 75, 75]), make_story(), pages, tmp_path
    )

    out = tmp_path / "demo" / "references" / "花花.jpg"
    assert written[0].path == out
    assert out.is_file()
    with Image.open(out) as image:
        # Half of the page, plus the margin on both sides.
        assert image.size == (648, 648)
        assert written[0].width == 648


def test_small_crop_is_raised_to_the_minimum_side(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    written = save_references(
        make_content([40, 40, 60, 60]), make_story(), pages, tmp_path
    )

    # 260 px wide, so a 1.15x zoom lands exactly on the minimum.
    assert (written[0].width, written[0].height) == (300, 300)


def test_crop_too_small_to_fix_is_skipped(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    content = make_content([40, 40, 48, 48])

    written = save_references(content, make_story(), pages, tmp_path)

    # 104 px wide; even the capped zoom stays under the minimum.
    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_full_page_box_stays_inside_the_image(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    written = save_references(
        make_content([0, 0, 100, 100]), make_story(), pages, tmp_path
    )

    assert (written[0].width, written[0].height) == (SIDE, SIDE)


def test_a_missing_box_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    content = make_content(None)

    written = save_references(content, make_story(), pages, tmp_path)

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_reversed_box_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    content = make_content([60, 60, 40, 40])

    written = save_references(content, make_story(), pages, tmp_path)

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_flat_box_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    content = make_content([25, 25, 75, 25])

    written = save_references(content, make_story(), pages, tmp_path)

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_box_beyond_100_percent_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    # A model may emit a percentage past the page; clamping leaves no area.
    content = make_content([150, 150, 200, 200])

    written = save_references(content, make_story(), pages, tmp_path)

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_missing_page_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    story = Story(
        id="demo",
        characters=["花花"],
        references=[Reference("花花", 9, 0, "全身正面")],
    )

    written = save_references(
        make_content([25, 25, 75, 75]), story, pages, tmp_path
    )

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_missing_figure_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    story = Story(
        id="demo",
        characters=["花花"],
        references=[Reference("花花", 1, 3, "全身正面")],
    )

    written = save_references(
        make_content([25, 25, 75, 75]), story, pages, tmp_path
    )

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_missing_page_image_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir(parents=True)

    written = save_references(
        make_content([25, 25, 75, 75]), make_story(), pages, tmp_path
    )

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_a_broken_page_image_writes_nothing(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir(parents=True)
    (pages / "page_001.jpg").write_bytes(b"not an image")

    written = save_references(
        make_content([25, 25, 75, 75]), make_story(), pages, tmp_path
    )

    assert written == []
    assert list((tmp_path / "demo" / "references").iterdir()) == []


def test_old_crops_are_removed(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)
    stale = tmp_path / "demo" / "references" / "旧角色.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")

    content = make_content([25, 25, 75, 75])

    save_references(content, make_story(), pages, tmp_path)

    assert not stale.exists()


def test_crop_outside_the_allowed_ratio_is_skipped(tmp_path):
    pages = tmp_path / "pages"
    make_page(pages)

    content = make_content([45, 0, 55, 100])

    written = save_references(content, make_story(), pages, tmp_path)

    # 130x1200 is far narrower than a video model accepts.
    assert written == []
