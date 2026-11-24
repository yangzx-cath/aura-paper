"""The book list and the PDF upload."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from aura_paper.store.books import import_pdf, list_books, status_of

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/books")
def books() -> dict:
    """Return every book with the status the shelf should show."""
    rows = []
    for meta in list_books():
        row = meta.to_dict()
        row["status"] = status_of(meta.id)
        rows.append(row)
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

    row = meta.to_dict()
    row["status"] = status_of(meta.id)
    return row
