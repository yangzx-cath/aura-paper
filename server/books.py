"""The book list and the PDF upload."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from aura_paper.store.books import BookMeta, import_pdf, list_books, status_of

OUT = Path(__file__).resolve().parent.parent / "out"

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/books")
def books() -> dict:
    """Return every book with the status the shelf should show."""
    rows = []
    for meta in list_books():
        rows.append(_row(meta))
    return {"books": rows}


@router.post("/books")
async def upload(file: UploadFile = File(...)) -> dict:
    """Store one PDF under the next free id. It is not analysed here."""
    try:
        meta = await run_in_threadpool(
            import_pdf,
            file.file,
            file.filename or "book.pdf",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _row(meta)


# One book as the shelf needs it, cover path included.
def _row(meta: BookMeta) -> dict:
    row = meta.to_dict()
    row["status"] = status_of(meta.id)
    cover = OUT / meta.id / "cover.jpg"
    row["cover"] = f"/media/{meta.id}/cover.jpg" if cover.is_file() else ""
    return row
