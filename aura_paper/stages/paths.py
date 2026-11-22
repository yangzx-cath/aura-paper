"""Where each stage reads and writes its artifacts."""

from __future__ import annotations

from pathlib import Path

from ..config import out_root


def book_dir(book_id: str, root: str | Path | None = None) -> Path:
    """Return <root>/<book_id>, defaulting to the out root."""
    base = Path(root) if root is not None else out_root()
    return base / book_id


def panels_dir(book_id: str, root: str | Path | None = None) -> Path:
    """Return the folder holding one image per panel."""
    return book_dir(book_id, root) / "panels"


def figures_dir(book_id: str, root: str | Path | None = None) -> Path:
    """Return the folder holding one image per figure candidate."""
    return book_dir(book_id, root) / "figures"


def thumbs_dir(book_id: str, root: str | Path | None = None) -> Path:
    """Return the folder holding the small copies sent to the model."""
    return book_dir(book_id, root) / "thumbs"


def panel_name(page_name: str, index: int) -> str:
    """Return the panel image name for one page image name."""
    return f"{Path(page_name).stem}_{index}.jpg"


def figure_name(page_name: str, index: int) -> str:
    """Return the figure image name for one page image name."""
    return f"{Path(page_name).stem}_f{index}.jpg"
