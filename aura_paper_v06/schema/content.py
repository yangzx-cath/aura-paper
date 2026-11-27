"""Page content read from the page images."""

from __future__ import annotations

from dataclasses import dataclass, field

from .time import now_iso

# A panel below this share of the page needs a scene behind it.
NEEDS_SCENE_AREA = 0.5


@dataclass
class CoverContent:
    """The book details read from the cover."""

    title: str = ""
    author: str = ""
    illustrator: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this cover."""
        return {
            "title": self.title,
            "author": self.author,
            "illustrator": self.illustrator,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CoverContent:
        """Build a cover from its external JSON shape."""
        return cls(
            title=_text(data.get("title")),
            author=_text(data.get("author")),
            illustrator=_text(data.get("illustrator")),
        )


# Read one text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


@dataclass
class Figure:
    """One figure on one page, which may or may not be a cast member."""

    index: int = 0
    name: str = ""
    body: str = ""
    outfit: str = ""
    view: str = ""
    facing: str = ""
    occlusion: str = ""
    box: list[int] | None = None  # [left, top, right, bottom], per-mille
    panel: int = -1  # index of the panel this figure sits in

    def to_dict(self) -> dict:
        """Return the external JSON shape of this figure."""
        return {
            "index": self.index,
            "name": self.name,
            "body": self.body,
            "outfit": self.outfit,
            "view": self.view,
            "facing": self.facing,
            "occlusion": self.occlusion,
            "box": self.box,
            "panel": self.panel,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Figure:
        """Build a figure from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            name=_text(data.get("name")),
            body=_text(data.get("body")),
            outfit=_text(data.get("outfit")),
            view=_text(data.get("view")),
            facing=_text(data.get("facing")),
            occlusion=_text(data.get("occlusion")),
            box=_box_value(data.get("box")),
            panel=_panel_index(data.get("panel")),
        )


# Read a panel number, defaulting to -1 when the model gave none.
def _panel_index(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1


# Read a crop box as [left, top, right, bottom] in per-mille, or None.
def _box_value(value: object) -> list[int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    numbers = []
    for item in value:
        if not isinstance(item, (int, float)):
            return None
        numbers.append(int(min(1000, max(0, item))))
    left, top, right, bottom = numbers
    if right <= left or bottom <= top:
        return None
    return numbers


@dataclass
class Panel:
    """One picture block inside a page."""

    index: int = 0
    box: list[int] | None = None
    text: str = ""
    description: str = ""
    needs_scene: bool = False

    def to_dict(self) -> dict:
        """Return the external JSON shape of this panel."""
        return {
            "index": self.index,
            "box": self.box,
            "text": self.text,
            "description": self.description,
            "needs_scene": self.needs_scene,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Panel:
        """Build a panel from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            box=_box_value(data.get("box")),
            text=_text(data.get("text")),
            description=_text(data.get("description")),
            needs_scene=bool(data.get("needs_scene")),
        )


# Tell whether a panel is too small to carry its own environment.
def _needs_scene(box: list[int] | None) -> bool:
    if box is None:
        return True
    left, top, right, bottom = box
    share = (right - left) * (bottom - top) / (1000 * 1000)
    return share < NEEDS_SCENE_AREA


@dataclass
class PageContent:
    """Structured content of one page."""

    index: int
    filename: str
    width: int = 0
    height: int = 0
    page_text: str = ""
    meta_text: str = ""
    light: str = ""
    description: str = ""
    panels: list[Panel] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        return {
            "index": self.index,
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "model": self.model,
            "generated_at": now_iso(),
            "page_text": self.page_text,
            "meta_text": self.meta_text,
            "light": self.light,
            "description": self.description,
            "panels": [panel.to_dict() for panel in self.panels],
            "figures": [figure.to_dict() for figure in self.figures],
            "uncertain": self.uncertain,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PageContent:
        """Build a page from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            filename=str(data.get("filename") or ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            page_text=_text(data.get("page_text")),
            meta_text=_text(data.get("meta_text")),
            light=_text(data.get("light")),
            description=_text(data.get("description")),
            panels=_panel_list(data.get("panels")),
            figures=_figure_list(data.get("figures")),
            uncertain=_text_list(data.get("uncertain")),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


# Read the panel list, numbering the entries by their order on the page.
def _panel_list(value: object) -> list[Panel]:
    if not isinstance(value, list):
        return []
    panels = []
    for item in value:
        if not isinstance(item, dict):
            continue
        panel = Panel.from_dict(item)
        # A panel without a usable box cannot be cropped, so drop it.
        if panel.box is not None:
            panels.append(panel)
    for index, panel in enumerate(panels):
        panel.index = index
        panel.needs_scene = _needs_scene(panel.box)
    return panels


# Read the figure list, numbering the entries by their order on the page.
def _figure_list(value: object) -> list[Figure]:
    if not isinstance(value, list):
        return []
    figures = [
        Figure.from_dict(item) for item in value if isinstance(item, dict)
    ]
    for index, figure in enumerate(figures):
        figure.index = index
    return figures


# Read the note list, keeping one line per text entry.
def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    texts = []
    for item in value:
        if isinstance(item, (dict, list)):
            continue
        text = str(item).strip()
        if text:
            texts.append(text)
    return texts


# Tell whether a text is written in Chinese or English.
def language_of(text: str) -> str:
    """Return "zh" or "en" from the letters in text."""
    han = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    return "en" if latin > han else "zh"


@dataclass
class BookContent:
    """Structured content of a whole book."""

    id: str
    source: str
    cover: CoverContent = field(default_factory=CoverContent)
    pages: list[PageContent] = field(default_factory=list)

    @property
    def title(self) -> str:
        """Return the title printed on the cover."""
        return self.cover.title

    @property
    def page_count(self) -> int:
        """Return the number of pages, the cover included."""
        return len(self.pages)

    @property
    def failed_count(self) -> int:
        """Return how many pages failed, the cover included."""
        return sum(1 for page in self.pages if page.error)

    @property
    def cover_page(self) -> PageContent | None:
        """Return the first page, which is the cover."""
        return self.pages[0] if self.pages else None

    @property
    def story_pages(self) -> list[PageContent]:
        """Return the pages after the cover, which carry the story."""
        return self.pages[1:]

    @property
    def language(self) -> str:
        """Return "zh" or "en" from the words the book carries."""
        text = self.cover.title
        text += "".join(page.page_text for page in self.pages)
        return language_of(text)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "generated_at": now_iso(),
            "page_count": self.page_count,
            "failed_count": self.failed_count,
            "cover": self.cover.to_dict(),
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookContent:
        """Build a book from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            source=str(data.get("source") or ""),
            cover=CoverContent.from_dict(data.get("cover") or {}),
            pages=[
                PageContent.from_dict(page) for page in data.get("pages") or []
            ],
        )
