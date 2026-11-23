"""Who appears in each panel of a page, and what part of them shows."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso


@dataclass
class PanelPerson:
    """One character in one panel, and the part of them that shows."""

    cast: str = ""
    parts: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this person."""
        return {"cast": self.cast, "parts": self.parts}

    @classmethod
    def from_dict(cls, data: dict) -> PanelPerson:
        """Build a person from their external JSON shape."""
        return cls(
            cast=_text(data.get("cast")),
            parts=_text(data.get("parts")),
        )


@dataclass
class PanelPeople:
    """The characters one panel shows."""

    page: str = ""
    panel: int = 0
    people: list[PanelPerson] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this panel."""
        return {
            "page": self.page,
            "panel": self.panel,
            "people": [person.to_dict() for person in self.people],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PanelPeople:
        """Build a panel from its external JSON shape."""
        return cls(
            page=_text(data.get("page")),
            panel=_int_value(data.get("panel")),
            people=_people_list(data.get("people")),
        )


@dataclass
class BookPeople:
    """The panels of one book that needed a closer look at who is in them."""

    id: str = ""
    model: str = ""
    panels: list[PanelPeople] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these panels."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "panels": [panel.to_dict() for panel in self.panels],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookPeople:
        """Build the panels from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            model=_text(data.get("model")),
            panels=_panel_list(data.get("panels")),
            error=_text(data.get("error")),
        )


# Read a text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read an integer, falling back to zero when the value is unusable.
def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read the people of one panel, keeping the ones with a cast id.
def _people_list(value: object) -> list[PanelPerson]:
    if not isinstance(value, list):
        return []
    people = [
        PanelPerson.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [person for person in people if person.cast]


# Read the panels of one book, keeping the entries that name a page.
def _panel_list(value: object) -> list[PanelPeople]:
    if not isinstance(value, list):
        return []
    panels = [
        PanelPeople.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [panel for panel in panels if panel.page]
