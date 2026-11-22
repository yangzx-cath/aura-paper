"""Read every page image into structured content."""

from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from ..cache import Cache, file_fingerprint, fingerprint
from ..clients.llm import LLMClient, LLMError
from ..media.image import crop_box, load_image, save_jpeg
from ..output import write_json
from ..prompts import cover_prompt, page_prompt
from ..schema.book import Book as IngestBook
from ..schema.book import Page as IngestPage
from ..schema.content import BookContent, CoverContent, PageContent, Panel
from ..utils import extract_json
from .paths import book_dir, panel_name, panels_dir

# Panels are cropped from the page once, so keep the second encode clean.
PANEL_QUALITY = 95


def understand(
    book_id: str,
    *,
    llm: LLMClient,
    root: str | Path | None = None,
    workers: int = 1,
    cache: Cache | None = None,
    on_page: Callable[[PageContent, float], None] | None = None,
) -> BookContent:
    """Read every page of an ingested book and write understand.json."""
    assert workers >= 1

    directory = book_dir(book_id, root)
    pages_dir = directory / "pages"
    ingest = _read_ingest(directory)
    content = BookContent(id=book_id, source=str(pages_dir))
    if not ingest.pages:
        return content

    ns = f"understand/{book_id}"

    def run(page: IngestPage) -> PageContent:
        started = time.perf_counter()
        result = _read_page(page, llm, cache, ns, pages_dir)
        if on_page is not None:
            on_page(result, time.perf_counter() - started)
        return result

    def run_cover(page: IngestPage) -> tuple[PageContent, CoverContent]:
        started = time.perf_counter()
        result, cover = _read_cover(page, llm, cache, ns, pages_dir)
        if on_page is not None:
            on_page(result, time.perf_counter() - started)
        return result, cover

    cover_page = ingest.pages[0]
    story = ingest.pages[1:]

    results: list[PageContent] = []
    if workers == 1:
        cover_content, cover = run_cover(cover_page)
        results.append(cover_content)
        for page in story:
            results.append(run(page))
    else:
        # The cover feeds no page, so it runs beside them instead of first.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            cover_future = pool.submit(run_cover, cover_page)
            # pool.map() keeps the input order, so pages stay in book order.
            story_results = list(pool.map(run, story))
            cover_content, cover = cover_future.result()
        results.append(cover_content)
        results.extend(story_results)

    content.cover = cover
    content.pages = results
    _save_panels(content.pages, pages_dir, panels_dir(book_id, root))
    write_json(book_id, "understand", content.to_dict(), root)
    return content


# Read the ingest stage's record of the book.
def _read_ingest(directory: Path) -> IngestBook:
    path = directory / "ingest.json"
    text = path.read_text(encoding="utf-8")
    return IngestBook.from_dict(json.loads(text))


# Read one page and reuse the cached answer when its inputs are unchanged.
def _read_page(
    page: IngestPage,
    llm: LLMClient,
    cache: Cache | None,
    ns: str,
    pages_dir: Path,
) -> PageContent:
    content = PageContent(
        index=page.index,
        filename=page.filename,
        width=page.width,
        height=page.height,
        model=llm.model,
    )
    prompt = page_prompt()
    path = pages_dir / page.filename

    if cache is None:
        return _ask_page(content, llm, prompt, path)

    name = Path(page.filename).stem
    digest = file_fingerprint(path)
    key = fingerprint(digest, prompt, *llm.signature)
    entry = cache.load_json(ns, name, key)
    if entry is not None:
        _apply_fields(content, entry)
        return content

    content = _ask_page(content, llm, prompt, path)
    # Errors are never cached, so a failed page is retried next run.
    if not content.error:
        cache.save_json(ns, name, key, _page_fields(content))
    return content


# Call the model for one page and fill the result fields.
def _ask_page(
    content: PageContent,
    llm: LLMClient,
    prompt: str,
    path: Path,
) -> PageContent:
    try:
        reply = llm.chat(prompt, image_path=path)
        fields = extract_json(reply)
    except (LLMError, ValueError) as exc:
        content.error = str(exc)
        return content

    _apply_fields(content, fields)
    if not content.panels and not content.meta_text:
        content.error = "model returned no content"
    return content


# Copy the model fields, turning missing or null values into empty strings.
def _apply_fields(content: PageContent, fields: dict) -> None:
    parsed = PageContent.from_dict(fields)
    content.meta_text = parsed.meta_text
    content.light = parsed.light
    content.panels = parsed.panels
    content.figures = parsed.figures
    content.uncertain = parsed.uncertain
    content.page_text = _panel_text(parsed.panels)


# Join the panel texts, which are the only copy of the story words.
def _panel_text(panels: list[Panel]) -> str:
    return "\n".join(panel.text for panel in panels if panel.text)


# Read the model's figures and notes into the page shape.
def _page_fields(content: PageContent) -> dict:
    return {
        "meta_text": content.meta_text,
        "light": content.light,
        "panels": [panel.to_dict() for panel in content.panels],
        "figures": [figure.to_dict() for figure in content.figures],
        "uncertain": content.uncertain,
    }


# Read the cover and reuse the cached answer when its inputs are unchanged.
def _read_cover(
    page: IngestPage,
    llm: LLMClient,
    cache: Cache | None,
    ns: str,
    pages_dir: Path,
) -> tuple[PageContent, CoverContent]:
    content = PageContent(
        index=page.index,
        filename=page.filename,
        width=page.width,
        height=page.height,
        model=llm.model,
    )
    cover = CoverContent()
    prompt = cover_prompt()
    path = pages_dir / page.filename

    if cache is None:
        return _ask_cover(content, cover, llm, prompt, path)

    name = Path(page.filename).stem
    digest = file_fingerprint(path)
    key = fingerprint(digest, prompt, *llm.signature)
    entry = cache.load_json(ns, name, key)
    if entry is not None:
        _apply_cover(content, cover, entry)
        return content, cover

    content, cover = _ask_cover(content, cover, llm, prompt, path)
    # Errors are never cached, so a failed cover is retried next run.
    if not content.error:
        cache.save_json(ns, name, key, _cover_fields(content, cover))
    return content, cover


# Call the model for the cover and fill the page content and book details.
def _ask_cover(
    content: PageContent,
    cover: CoverContent,
    llm: LLMClient,
    prompt: str,
    path: Path,
) -> tuple[PageContent, CoverContent]:
    try:
        reply = llm.chat(prompt, image_path=path)
        fields = extract_json(reply)
    except (LLMError, ValueError) as exc:
        content.error = str(exc)
        return content, cover

    _apply_cover(content, cover, fields)
    if not cover.title and not content.description:
        content.error = "model returned no content"
    return content, cover


# Copy the cover fields, turning missing or null values into empty strings.
def _apply_cover(
    content: PageContent,
    cover: CoverContent,
    fields: dict,
) -> None:
    content.description = str(fields.get("description") or "")
    cover.title = str(fields.get("title") or "")
    cover.author = str(fields.get("author") or "")
    cover.illustrator = str(fields.get("illustrator") or "")


# Read the model's cover fields into the cache shape.
def _cover_fields(content: PageContent, cover: CoverContent) -> dict:
    return {
        "title": cover.title,
        "author": cover.author,
        "illustrator": cover.illustrator,
        "description": content.description,
    }


# Crop every panel to its own file, so later stages crop nothing.
def _save_panels(
    pages: list[PageContent],
    pages_dir: Path,
    out_dir: Path,
) -> None:
    shutil.rmtree(out_dir, ignore_errors=True)
    for page in pages:
        if not page.panels:
            continue
        image = load_image(pages_dir / page.filename)
        for panel in page.panels:
            box = panel.box
            if box is None:
                continue
            left, top, right, bottom = box
            name = panel_name(page.filename, panel.index)
            crop = crop_box(image, (left, top, right, bottom))
            save_jpeg(crop, out_dir / name, PANEL_QUALITY)
