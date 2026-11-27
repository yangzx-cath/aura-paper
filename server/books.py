"""The book list the studio shelf shows."""

from __future__ import annotations

from fastapi import APIRouter

from aura_paper.store.books import list_books, status_of

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/books")
def books() -> dict:
    """Return every book with the status the shelf shows."""
    rows = []
    for meta in list_books():
        row = meta.to_dict()
        row["status"] = status_of(meta.id)
        rows.append(row)
    return {"books": rows}
