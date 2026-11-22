"""Turn the panels into scenes and shots, with the sound of each shot."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from ..cache import Cache, file_fingerprint, fingerprint
from ..clients.llm import LLMClient, LLMError
from ..media.image import load_image, save_jpeg, thumbnail
from ..output import write_json
from ..prompts import storyboard_prompt
from ..schema.cast import BookCast
from ..schema.content import BookContent, PageContent
from ..schema.location import BookLocations
from ..schema.storyboard import (
    SHOT_JOINS,
    SHOT_MODES,
    BookStoryboard,
    Scene,
    Shot,
)
from ..utils import extract_json
from .paths import (
    book_dir,
    figures_dir,
    panel_name,
    panels_dir,
    thumbs_dir,
)

# The model reads a small copy of each image, which is enough to spot who
# is in the frame and what the panel shows.
THUMB_BOX = (512, 512)

# The crops are already encoded, so a light second encode is enough.
THUMB_QUALITY = 90


def storyboard(
    book_id: str,
    *,
    llm: LLMClient,
    root: str | Path | None = None,
    cache: Cache | None = None,
) -> BookStoryboard:
    """Read three artifacts, plan the scenes and shots, write the file."""
    directory = book_dir(book_id, root)
    pages = _read_content(directory).pages
    cast_book = _read_cast(directory)
    places = _read_locations(directory)

    result = BookStoryboard(
        id=book_id,
        model=llm.model,
        style=places.style,
    )
    panels = _panel_images(book_id, pages, root)
    refs = _ref_images(book_id, cast_book, root)
    prompt = storyboard_prompt(pages, cast_book, places, panels, refs)
    images = _thumbs(book_id, panels, refs, root)

    try:
        fields = _ask(llm, prompt, images, cache, book_id)
    except (LLMError, ValueError) as exc:
        result.error = str(exc)
        write_json(book_id, "storyboard", result.to_dict(), root)
        return result

    _apply(result, fields, pages, cast_book)
    if not result.shots:
        result.error = _joined(result.error, "model returned no shot")
    write_json(book_id, "storyboard", result.to_dict(), root)
    return result


# List the panels that have a crop, in reading order.
def _panel_images(
    book_id: str,
    pages: list[PageContent],
    root: str | Path | None,
) -> list[tuple[str, int, str]]:
    folder = panels_dir(book_id, root)
    kept = []
    for page in pages:
        for panel in page.panels:
            if panel.box is None:
                continue
            crop = panel_name(page.filename, panel.index)
            if not (folder / crop).is_file():
                continue
            kept.append((page.filename, panel.index, crop))
    return kept


# Pick one crop per character, in the order the characters are listed.
def _ref_images(
    book_id: str,
    cast_book: BookCast,
    root: str | Path | None,
) -> list[tuple[str, str]]:
    folder = figures_dir(book_id, root)
    kept = []
    for member in cast_book.cast:
        for name in member.pictures:
            if (folder / name).is_file():
                kept.append((member.id, name))
                break
    return kept


# Shrink the images the model reads and return them in prompt order.
def _thumbs(
    book_id: str,
    panels: list[tuple[str, int, str]],
    refs: list[tuple[str, str]],
    root: str | Path | None,
) -> list[Path]:
    out_dir = thumbs_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)

    sources = [panels_dir(book_id, root) / crop for _, _, crop in panels]
    sources += [figures_dir(book_id, root) / name for _, name in refs]

    kept = []
    for path in sources:
        target = out_dir / path.name
        save_jpeg(
            thumbnail(load_image(path), THUMB_BOX), target, THUMB_QUALITY
        )
        kept.append(target)
    return kept


# Read the plan, reusing the cached one when nothing changed.
def _ask(
    llm: LLMClient,
    prompt: str,
    images: list[Path],
    cache: Cache | None,
    book_id: str,
) -> dict:
    if cache is None:
        return _chat(llm, prompt, images)

    ns = f"storyboard/{book_id}"
    key = _key(images, prompt, llm)
    entry = cache.load_json(ns, "plan", key)
    if entry is not None:
        return entry

    fields = _chat(llm, prompt, images)
    cache.save_json(ns, "plan", key, fields)
    return fields


# Send the panels and the references, and read the reply as JSON.
def _chat(llm: LLMClient, prompt: str, images: list[Path]) -> dict:
    return extract_json(llm.chat(prompt, images=images))


# Fingerprint the images, the prompt and the model, so the key is exact.
def _key(images: list[Path], prompt: str, llm: LLMClient) -> str:
    digests = [file_fingerprint(path) for path in images]
    return fingerprint(*digests, prompt, *llm.signature)


# Turn the plan into scenes and shots, filling what the model left out.
def _apply(
    result: BookStoryboard,
    fields: dict,
    pages: list[PageContent],
    cast_book: BookCast,
) -> None:
    page_names = {page.filename for page in pages}
    panels = {
        (page.filename, panel.index): panel
        for page in pages
        for panel in page.panels
    }
    cast_ids = {member.id for member in cast_book.cast}

    scenes, keys = _scenes(fields, page_names)
    shots, notes = _shots(fields, keys, panels, cast_ids)

    result.scenes = scenes
    result.shots = _joins(shots)
    missed = _printed(result.shots, panels)
    unknown = sum(
        1 for shot in result.shots for line in shot.audio if not line.kind
    )
    voiceless = sum(
        1
        for shot in result.shots
        for line in shot.audio
        if line.kind == "对白" and not line.cast
    )
    if unknown:
        notes.append(f"{unknown} 条声音的类型不认识")
    if voiceless:
        notes.append(f"{voiceless} 句对白没有说话人")
    if missed:
        notes.append(f"{missed} 行文字在原文里找不到")
    if notes:
        result.error = _joined(result.error, "；".join(notes))


# Number the scenes and remember the tags the shots point at.
def _scenes(
    fields: dict,
    page_names: set[str],
) -> tuple[list[Scene], dict[str, str]]:
    entries = []
    keys: dict[str, str] = {}
    for entry in fields.get("scenes") or []:
        if not isinstance(entry, dict):
            continue
        scene_id = f"s{len(entries) + 1}"
        key = str(entry.get("key") or "").strip()
        if key:
            keys[key] = scene_id
        entries.append(
            {
                "id": scene_id,
                "name": entry.get("name"),
                "location": entry.get("location"),
                "pages": [
                    str(page).strip()
                    for page in entry.get("pages") or []
                    if str(page).strip() in page_names
                ],
            }
        )
    parsed = BookStoryboard.from_dict({"scenes": entries})
    return parsed.scenes, keys


# Number the shots, resolve their scene and keep the cast that exists.
def _shots(
    fields: dict,
    keys: dict[str, str],
    panels: dict[tuple[str, int], object],
    cast_ids: set[str],
) -> tuple[list[Shot], list[str]]:
    entries = []
    notes = []
    for entry in fields.get("shots") or []:
        if not isinstance(entry, dict):
            continue
        page_name = str(entry.get("page") or "").strip()
        index = _int(entry.get("panel"))
        panel = panels.get((page_name, index))
        if panel is None:
            notes.append(f"{page_name} 第 {index} 块不存在")
            continue
        entries.append(
            {
                "id": f"j{len(entries) + 1}",
                "scene": keys.get(str(entry.get("scene") or "").strip(), ""),
                "page": page_name,
                "panel": index,
                "cast": [
                    cast_id
                    for cast_id in _texts(entry.get("cast"))
                    if cast_id in cast_ids
                ],
                "mode": _mode(entry, panel),
                "join": str(entry.get("join") or "").strip(),
                "camera": entry.get("camera"),
                "beats": entry.get("beats"),
                "audio": _audio(entry.get("audio"), cast_ids),
                "continuity": entry.get("continuity"),
            }
        )
    parsed = BookStoryboard.from_dict({"shots": entries})
    return parsed.shots, notes


# A panel without a background can only be widened, never used as a frame.
def _mode(entry: dict, panel: object) -> str:
    if getattr(panel, "needs_scene", False):
        return "扩景"
    mode = str(entry.get("mode") or "").strip()
    return mode if mode in SHOT_MODES else "首帧"


# Keep one voice per line, because one line is one sentence of speech.
def _audio(value: object, cast_ids: set[str]) -> list[dict]:
    if not isinstance(value, list):
        return []
    lines = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        lines.append(
            {
                "kind": entry.get("kind"),
                "text": entry.get("text"),
                "cast": _voice(entry.get("cast"), cast_ids),
            }
        )
    return lines


# Pick the one voice of a line out of whatever the model wrote.
def _voice(value: object, cast_ids: set[str]) -> str:
    parts = (
        value
        if isinstance(value, list)
        else re.split(r"[、,，\s]+", str(value or ""))
    )
    for part in parts:
        name = str(part).strip()
        if name in cast_ids:
            return name
    return ""


# Fill a missing join from whether the shot before it stays in the same scene.
def _joins(shots: list[Shot]) -> list[Shot]:
    for number, shot in enumerate(shots):
        if shot.join in SHOT_JOINS:
            continue
        before = shots[number - 1] if number else None
        shot.join = "硬切" if before and before.scene == shot.scene else "叠化"
    return shots


# Match every sound back to the printed text, so nothing is paraphrased.
def _printed(shots: list[Shot], panels: dict) -> int:
    missed = 0
    for shot in shots:
        panel = panels.get((shot.page, shot.panel))
        source = getattr(panel, "text", "") or ""
        for line in shot.audio:
            exact = _as_printed(line.text, source)
            if exact is None:
                missed += 1
                continue
            line.text = exact
    return missed


# Return the printed form of a line, or None when the page does not hold it.
def _as_printed(text: str, source: str) -> str | None:
    wanted = "".join(char for char in text if not char.isspace())
    if not wanted:
        return None

    squeezed = []
    positions = []
    for position, char in enumerate(source):
        if char.isspace():
            continue
        squeezed.append(char)
        positions.append(position)

    start = "".join(squeezed).find(wanted)
    if start < 0:
        return None
    end = positions[start + len(wanted) - 1]
    return source[positions[start] : end + 1]


# Read the understand stage's record of the book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    return BookContent.from_dict(json.loads(path.read_text(encoding="utf-8")))


# Read the cast stage's record of the characters.
def _read_cast(directory: Path) -> BookCast:
    path = directory / "cast.json"
    return BookCast.from_dict(json.loads(path.read_text(encoding="utf-8")))


# Read the place stage's record of the places and the art style.
def _read_locations(directory: Path) -> BookLocations:
    path = directory / "locations.json"
    text = path.read_text(encoding="utf-8")
    return BookLocations.from_dict(json.loads(text))


# Read a list of identifiers, dropping the empty ones.
def _texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    texts = (str(item or "").strip() for item in value)
    return [text for text in texts if text]


# Read an integer, falling back to -1 when the value is unusable.
def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1


# Join two error texts into one line.
def _joined(first: str, second: str) -> str:
    if not first:
        return second
    return f"{first}；{second}"
