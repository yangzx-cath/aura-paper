"""The book list, one book and the PDF upload."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from aura_paper.config import output_root
from aura_paper.store.books import (
    BOOK_ID_PATTERN,
    TITLE_FROM_FILENAME,
    BookMeta,
    import_pdf,
    list_books,
    read_book_meta,
    status_of,
)

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/books")
def books() -> dict:
    """Return every book in the library."""
    rows = []
    for meta in list_books():
        row = _row(meta)
        rows.append(row)
    return {"books": rows}


@router.get("/books/{book_id}")
def book(book_id: str) -> dict:
    """Return one book, or 404 when the library has no such id."""
    if not BOOK_ID_PATTERN.match(book_id):
        raise HTTPException(status_code=404, detail="没有这本书")
    meta = read_book_meta(book_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="没有这本书")
    return _row(meta)


@router.post("/books")
async def upload(file: UploadFile = File(...)) -> dict:
    """Store one PDF under the next free id. Nothing is analyzed here."""
    try:
        meta = await run_in_threadpool(
            import_pdf,
            file.file,
            file.filename or "book.pdf",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"写入书库失败 {exc.strerror or exc}",
        ) from exc
    return _row(meta)


# One book with the status, label and cover filled in.
def _row(meta: BookMeta) -> dict:
    row = meta.to_dict()
    row["status"] = status_of(meta.id)
    row["label"] = _label(meta)
    row["cover"] = _cover(meta.id)
    return row


# Until the title is read from the pages, the file name stands in for it.
def _label(meta: BookMeta) -> str:
    if meta.title_source == TITLE_FROM_FILENAME:
        return meta.filename or meta.title
    return meta.title or meta.filename


# The cover URL, empty until a cover file exists.
def _cover(book_id: str) -> str:
    if (output_root() / book_id / "cover.jpg").is_file():
        return f"/media/{book_id}/cover.jpg"
    return ""
