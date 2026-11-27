"""The book library, one folder per book."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ..clock import now_iso
from ..config import books_dir
from .artifacts import read_json, write_json

# Books are numbered in import order.
ID_PATTERN = re.compile(r"^B(\d{3,})$")

# The status of a book that is stored but not analyzed yet.
STATUS_UPLOADED = "uploaded"

# Where a book's title came from.
TITLE_FROM_FILENAME = "filename"
TITLE_FROM_BREAKDOWN = "breakdown"
TITLE_FROM_USER = "user"

# The uploaded PDF, kept beside the record.
SOURCE_NAME = "source.pdf"

# The record the library keeps for one book.
BOOK_NAME = "book.json"

# The latest run of each stage.
RUNS_NAME = "runs.json"

# One upload is a picture book, so 200MB is already generous.
MAX_BYTES = 200 * 1024 * 1024

# The bytes that mark a file as a PDF.
PDF_HEADER = b"%PDF-"


@dataclass
class BookMeta:
    """The library record of one book."""

    id: str = ""
    title: str = ""
    title_source: str = TITLE_FROM_FILENAME
    filename: str = ""
    imported_at: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this book."""
        return {
            "id": self.id,
            "title": self.title,
            "title_source": self.title_source,
            "filename": self.filename,
            "imported_at": self.imported_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BookMeta:
        """Build a book from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            title_source=str(data.get("title_source") or TITLE_FROM_FILENAME),
            filename=str(data.get("filename") or ""),
            imported_at=str(data.get("imported_at") or ""),
            error=str(data.get("error") or ""),
        )


def import_pdf(
    stream: BinaryIO,
    filename: str,
    *,
    root: str | Path | None = None,
) -> BookMeta:
    """Store one uploaded PDF under the next free id. Nothing is analyzed."""
    name = Path(filename).name
    if Path(name).suffix.lower() != ".pdf":
        raise ValueError("只接受 PDF 文件")

    book_id = _next_id(root)
    folder = _book_folder(book_id, root)
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
        )
        write_json(book_id, "book", meta.to_dict(), root or books_dir())
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return meta


# The smallest id above every book already in the library.
def _next_id(root: str | Path | None = None) -> str:
    base = Path(root) if root is not None else books_dir()
    highest = 0
    if base.is_dir():
        for path in base.iterdir():
            match = ID_PATTERN.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"B{highest + 1:03d}"


# The folder that holds one book.
def _book_folder(book_id: str, root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else books_dir()
    return base / book_id


# Copy one upload to disk, refusing anything that is not a real PDF.
def _copy(stream: BinaryIO, target: Path) -> int:
    # Some PDFs carry junk before the header, so it is searched in the
    # first KB instead of matched at the start.
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
                limit = MAX_BYTES // (1024 * 1024)
                raise ValueError(f"文件超过 {limit}MB")
            out.write(chunk)
    return size


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
    """Return the stored book, or None when it cannot be read."""
    path = _book_folder(book_id, root) / BOOK_NAME
    try:
        data = read_json(path)
    except ValueError:
        return None
    return BookMeta.from_dict(data)


def set_title(
    book_id: str,
    title: str,
    source: str = TITLE_FROM_BREAKDOWN,
    root: str | Path | None = None,
) -> bool:
    """Store a detected title unless someone typed one in by hand."""
    meta = read_meta(book_id, root)
    if meta is None or not title:
        return False
    if meta.title_source == TITLE_FROM_USER:
        return False
    meta.title = title
    meta.title_source = source
    write_json(book_id, "book", meta.to_dict(), root or books_dir())
    return True


def status_of(book_id: str, root: str | Path | None = None) -> str:
    """Return the status of one book."""
    folder = _book_folder(book_id, root)
    if _is_running(folder):
        return "running"
    meta = read_meta(book_id, root)
    if meta is not None and meta.error:
        return "failed"
    return STATUS_UPLOADED


# A record left as running means that stage is still going.
def _is_running(folder: Path) -> bool:
    try:
        data = read_json(folder / RUNS_NAME)
    except ValueError:
        return False
    for record in data.values():
        if isinstance(record, dict) and record.get("state") == "running":
            return True
    return False
