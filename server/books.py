"""The book list, the PDF upload and the published release."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from aura_paper.store.books import (
    ID_PATTERN,
    BookMeta,
    import_pdf,
    list_books,
    read_publish,
    release_folder,
    status_of,
)
from aura_paper.store.history import read as read_history

OUT = Path(__file__).resolve().parent.parent / "out"

# The files a release hands out, by the name the manifest records.
RELEASE_TYPES = {
    "film.mp4": "video/mp4",
    "subtitles.vtt": "text/vtt",
    "cover.jpg": "image/jpeg",
}

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


@router.get("/books/{book_id}/history")
def history(book_id: str) -> dict:
    """Return what the reader said and tapped in this book, newest first."""
    if not ID_PATTERN.match(book_id):
        raise HTTPException(status_code=404, detail="没有这本书")
    return {"history": read_history(book_id)}


@router.get("/books/{book_id}/publish")
def publish(book_id: str) -> dict:
    """Return the release manifest of one published book."""
    if not ID_PATTERN.match(book_id):
        raise HTTPException(status_code=404, detail="没有这本书")
    data = read_publish(book_id)
    if data is None:
        raise HTTPException(status_code=404, detail="这本书还没发布")
    return data


@router.get("/books/{book_id}/pub/{name}")
def release_file(book_id: str, name: str) -> FileResponse:
    """Return one published file, by the name the manifest records."""
    media = RELEASE_TYPES.get(name)
    if media is None or not ID_PATTERN.match(book_id):
        raise HTTPException(status_code=404, detail="没有这个文件")
    path = release_folder(book_id) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="没有这个文件")
    return FileResponse(path, media_type=media)


# One book as the shelf needs it, cover path included.
def _row(meta: BookMeta) -> dict:
    row = meta.to_dict()
    row["status"] = status_of(meta.id)
    cover = OUT / meta.id / "cover.jpg"
    row["cover"] = f"/media/{meta.id}/cover.jpg" if cover.is_file() else ""
    return row
