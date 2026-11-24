"""The book library: one folder per book under the books root."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from ..config import books_dir
from ..schema.time import now_iso
from .output import write_json

# Books are numbered in import order, so a name never comes from a filename.
ID_PATTERN = re.compile(r"^B(\d{3,})$")

# The id of a book that is stored but not analysed yet.
STATUS_UPLOADED = "uploaded"

# The PDF a reader will actually see, and the folder it lives in.
SOURCE_NAME = "source.pdf"
BOOK_NAME = "book.json"

# One upload is a picture book, so 200MB is already generous.
MAX_BYTES = 200 * 1024 * 1024

# A PDF may carry up to 1KB of junk before its header.
PDF_HEADER = b"%PDF-"


@dataclass
class BookMeta:
    """What the library knows about a book before it is analysed."""

    id: str = ""
    title: str = ""
    title_source: str = "filename"
    filename: str = ""
    imported_at: str = ""
    params: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book."""
        return {
            "id": self.id,
            "title": self.title,
            "title_source": self.title_source,
            "filename": self.filename,
            "imported_at": self.imported_at,
            "params": self.params,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookMeta:
        """Build a book from its external JSON shape."""
        params = data.get("params")
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            title_source=str(data.get("title_source") or "filename"),
            filename=str(data.get("filename") or ""),
            imported_at=str(data.get("imported_at") or ""),
            params=dict(params) if isinstance(params, dict) else {},
            error=str(data.get("error") or ""),
        )


def import_pdf(
    stream: BinaryIO,
    filename: str,
    *,
    root: str | Path | None = None,
    params: dict | None = None,
) -> BookMeta:
    """Store one uploaded PDF under the next free id. Nothing is analysed."""
    name = Path(filename).name
    if Path(name).suffix.lower() != ".pdf":
        raise ValueError("只接受 PDF 文件")

    book_id = next_id(root)
    folder = book_folder(book_id, root)
    folder.mkdir(parents=True)

    try:
        size = _copy(stream, folder / SOURCE_NAME)
        if not size:
            raise ValueError("文件是空的")
        meta = BookMeta(
            id=book_id,
            title=Path(name).stem,
            filename=name,
            imported_at=now_iso(),
            params=params or {},
        )
        write_json(book_id, "book", meta.to_dict(), root or books_dir())
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return meta


def list_books(root: str | Path | None = None) -> list[BookMeta]:
    """Read every book record in the library, oldest first."""
    base = Path(root) if root is not None else books_dir()
    if not base.is_dir():
        return []

    books = []
    for path in base.iterdir():
        if not path.is_dir():
            continue
        meta = read_meta(path.name, root)
        if meta is not None:
            books.append(meta)
    books.sort(key=lambda book: (book.imported_at, book.id))
    return books


def read_meta(book_id: str, root: str | Path | None = None) -> BookMeta | None:
    """Return the stored book, or None when the folder has no book.json."""
    path = book_folder(book_id, root) / BOOK_NAME
    if not path.is_file():
        return None
    try:
        return BookMeta.from_dict(_read_json(path))
    except ValueError:
        return None


def status_of(book_id: str, root: str | Path | None = None) -> str:
    """Return the one word the shelf shows under a book."""
    folder = book_folder(book_id, root)
    if _is_running(folder):
        return "running"
    if (folder / "pub" / "show.json").is_file():
        return "ready"
    meta = read_meta(book_id, root)
    if meta is not None and meta.error:
        return "failed"
    return STATUS_UPLOADED


def next_id(root: str | Path | None = None) -> str:
    """Return the smallest id above every book already in the library."""
    base = Path(root) if root is not None else books_dir()
    highest = 0
    if base.is_dir():
        for path in base.iterdir():
            match = ID_PATTERN.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"B{highest + 1:03d}"


def book_folder(book_id: str, root: str | Path | None = None) -> Path:
    """Return the folder holding one book's source, state and release."""
    base = Path(root) if root is not None else books_dir()
    return base / book_id


# run.json outlives a run, so only its state says the book is still running.
def _is_running(folder: Path) -> bool:
    path = folder / "run.json"
    if not path.is_file():
        return False
    try:
        return _read_json(path).get("state") == "running"
    except ValueError:
        return False


# Copy one upload to disk, refusing anything that is not a real PDF.
def _copy(stream: BinaryIO, target: Path) -> int:
    head = stream.read(1024)
    if PDF_HEADER not in head:
        raise ValueError("这不是 PDF 文件")
    stream.seek(0)

    size = 0
    with target.open("wb") as out:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("文件超过 200MB")
            out.write(chunk)
    return size


# Read one JSON file, raising ValueError when it is not an object.
def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data
