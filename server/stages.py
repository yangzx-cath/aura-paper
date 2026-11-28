"""The pipeline stages of one book."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from aura_paper.stages.registry import STAGES
from aura_paper.store.books import BOOK_ID_PATTERN, read_book_meta

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

router = APIRouter(prefix="/api", tags=["stages"])


@router.get("/books/{book_id}/stages")
def stages(book_id: str) -> dict:
    """Return every stage in run order, or 404 for an unknown book."""
    if not BOOK_ID_PATTERN.match(book_id):
        raise HTTPException(status_code=404, detail="没有这本书")
    meta = read_book_meta(book_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="没有这本书")

    rows = []
    for stage in STAGES:
        row = {
            "key": stage.key,
            "name": stage.name,
            "description": stage.description,
            "runnable": _has_script(stage.key),
        }
        rows.append(row)
    return {"stages": rows}


# A stage runs when its command line entry exists.
def _has_script(key: str) -> bool:
    return (SCRIPTS / f"run_{key}.py").is_file()
