"""The places of one book, the place of every panel, and the art style."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import now_iso


@dataclass
class Location:
    """One place in the book and the crop that shows it whole."""

    id: str = ""
    name: str = ""
    light: str = ""
    master: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this location."""
        return {
            "id": self.id,
            "name": self.name,
            "light": self.light,
            "master": self.master,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Location:
        """Build a location from its external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            name=_text(data.get("name")),
            light=_text(data.get("light")),
            master=_text(data.get("master")),
        )


@dataclass
class PanelLocation:
    """The place one panel happens in."""

    page: str = ""
    panel: int = 0
    location: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this panel place."""
        return {
            "page": self.page,
            "panel": self.panel,
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PanelLocation:
        """Build a panel place from its external JSON shape."""
        return cls(
            page=_text(data.get("page")),
            panel=_int_value(data.get("panel")),
            location=_text(data.get("location")),
        )


@dataclass
class BookLocations:
    """The places of one book, the place of every panel, and the style."""

    id: str = ""
    style: str = ""
    locations: list[Location] = field(default_factory=list)
    panel_locations: list[PanelLocation] = field(default_factory=list)
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of these places."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "style": self.style,
            "locations": [item.to_dict() for item in self.locations],
            "panel_locations": [
                item.to_dict() for item in self.panel_locations
            ],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookLocations:
        """Build the places from their external JSON shape."""
        return cls(
            id=_text(data.get("id")),
            style=_text(data.get("style")),
            locations=_location_list(data.get("locations")),
            panel_locations=_panel_location_list(data.get("panel_locations")),
            model=_text(data.get("model")),
            error=_text(data.get("error")),
        )


# Read every text field, trimming the whitespace around it.
def _text(value: object) -> str:
    return str(value or "").strip()


# Read an integer, falling back to zero when the value is unusable.
def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read the location list, keeping entries that carry an id.
def _location_list(value: object) -> list[Location]:
    if not isinstance(value, list):
        return []
    items = [
        Location.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.id]


# Read the panel places, keeping one entry per named page.
def _panel_location_list(value: object) -> list[PanelLocation]:
    if not isinstance(value, list):
        return []
    items = [
        PanelLocation.from_dict(item)
        for item in value
        if isinstance(item, dict)
    ]
    return [item for item in items if item.page]
