"""One image per panel, cut out of the page images."""

from __future__ import annotations

from dataclasses import dataclass, field

from .time import now_iso


@dataclass
class PanelCrop:
    """One panel and the file it was cut into."""

    page: str = ""
    index: int = 0
    file: str = ""
    box: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this panel."""
        return {
            "page": self.page,
            "index": self.index,
            "file": self.file,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PanelCrop:
        """Build a panel from its external JSON shape."""
        return cls(
            page=_text(data.get("page")),
            index=_int_value(data.get("index")),
            file=_text(data.get("file")),
            box=_box_value(data.get("box")),
        )


@dataclass
class PageCrop:
    """One page, and what the crop stage did to it."""

    filename: str = ""
    erased: bool = False
    lines: int = 0

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page."""
        return {
            "filename": self.filename,
            "erased": self.erased,
            "lines": self.lines,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PageCrop:
        """Build a page from its external JSON shape."""
        return cls(
            filename=_text(data.get("filename")),
            erased=bool(data.get("erased", False)),
            lines=_int_value(data.get("lines")),
        )


@dataclass
class BookCrop:
    """Every panel of one book, in reading order."""

    id: str = ""
    language: str = ""
    pages: list[PageCrop] = field(default_factory=list)
    panels: list[PanelCrop] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these crops."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "language": self.language,
            "pages": [page.to_dict() for page in self.pages],
            "panels": [panel.to_dict() for panel in self.panels],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookCrop:
        """Build the crops from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            language=_text(data.get("language")),
            pages=_page_list(data.get("pages")),
            panels=_panel_list(data.get("panels")),
            error=_text(data.get("error")),
        )


# Read a text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read a panel number, falling back to zero when the value is unusable.
def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read a crop box as [left, top, right, bottom], or an empty list.
def _box_value(value: object) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    numbers = []
    for item in value:
        if not isinstance(item, (int, float)):
            return []
        numbers.append(int(item))
    if len(numbers) != 4:
        return []
    return numbers


# Read the panel list, keeping the entries that name a file.
def _panel_list(value: object) -> list[PanelCrop]:
    if not isinstance(value, list):
        return []
    panels = [
        PanelCrop.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [panel for panel in panels if panel.file]


# Read the page list, keeping the entries that name a file.
def _page_list(value: object) -> list[PageCrop]:
    if not isinstance(value, list):
        return []
    pages = [
        PageCrop.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [page for page in pages if page.filename]
