"""Turn the panels into scenes and shots, with the sound of each shot."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from ..clients.llm import LLMClient, LLMError
from ..clients.reply import extract_json
from ..media.image import load_image, save_jpeg, thumbnail
from ..prompts import spoken_prompt, storyboard_prompt
from ..schema.cast import BookCast
from ..schema.content import BookContent, PageContent
from ..schema.identify import BookPeople
from ..schema.location import BookLocations
from ..schema.scene import BookScenes, Scene
from ..schema.shot import SHOT_JOINS, BookShots, Shot
from ..store.cache import Cache, file_fingerprint, fingerprint
from ..store.output import write_json
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
) -> tuple[BookScenes, BookShots]:
    """Read three artifacts, plan the scenes and shots, write two files."""
    directory = book_dir(book_id, root)
    pages = _read_content(directory).pages
    cast_book = _read_cast(directory)
    places = _read_locations(directory)
    people = _read_people(directory)

    scene_book = BookScenes(id=book_id, model=llm.model)
    shot_book = BookShots(
        id=book_id,
        model=llm.model,
        style=places.style,
    )
    panels = _panel_images(book_id, pages, root)
    refs = _ref_images(book_id, cast_book, root)
    prompt = storyboard_prompt(pages, cast_book, places, panels, refs, people)
    images = _thumbs(book_id, panels, refs, root)

    try:
        fields = _ask(llm, prompt, images, cache, book_id, "plan")
    except (LLMError, ValueError) as exc:
        scene_book.error = str(exc)
        shot_book.error = str(exc)
        _write(book_id, scene_book, shot_book, root)
        return scene_book, shot_book

    notes = _apply(fields, scene_book, shot_book, pages, cast_book, people)
    if not scene_book.scenes:
        notes.insert(0, "model returned no scene")
    if not shot_book.shots:
        notes.append("model returned no shot")
    _merge(shot_book.shots)
    notes += _spoken(shot_book.shots, cast_book, llm, cache, book_id, pages)
    if notes:
        shot_book.error = "；".join(notes)
    _write(book_id, scene_book, shot_book, root)
    return scene_book, shot_book


# Read the identify stage's record of the people in each panel, if any.
def _read_people(directory: Path) -> BookPeople:
    path = directory / "identify.json"
    if not path.is_file():
        return BookPeople()
    return BookPeople.from_dict(json.loads(path.read_text("utf-8")))


# Write the two files the later stages read.
def _write(
    book_id: str,
    scene_book: BookScenes,
    shot_book: BookShots,
    root: str | Path | None,
) -> None:
    write_json(book_id, "scenes", scene_book.to_dict(), root)
    write_json(book_id, "shots", shot_book.to_dict(), root)


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


# Read an answer, reusing the cached one when nothing changed.
def _ask(
    llm: LLMClient,
    prompt: str,
    images: list[Path],
    cache: Cache | None,
    book_id: str,
    name: str,
) -> dict:
    if cache is None:
        return _chat(llm, prompt, images)

    ns = f"storyboard/{book_id}"
    key = _key(images, prompt, llm)
    entry = cache.load_json(ns, name, key)
    if entry is not None:
        return entry

    fields = _chat(llm, prompt, images)
    cache.save_json(ns, name, key, fields)
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
    fields: dict,
    scene_book: BookScenes,
    shot_book: BookShots,
    pages: list[PageContent],
    cast_book: BookCast,
    people: BookPeople,
) -> list[str]:
    page_names = {page.filename for page in pages}
    panels = {
        (page.filename, panel.index): panel
        for page in pages
        for panel in page.panels
    }
    cast_ids = {member.id for member in cast_book.cast}

    scenes, keys = _scenes(fields, page_names)
    shots, notes = _shots(fields, keys, panels, cast_ids)

    scene_book.scenes = scenes
    shot_book.shots = _joins(shots)
    _fill_cast(shot_book.shots, people, cast_book)
    missed, repeated, moved = _printed(shot_book.shots, panels)
    unknown = sum(
        1 for shot in shot_book.shots for line in shot.audio if not line.kind
    )
    voiceless = sum(
        1
        for shot in shot_book.shots
        for line in shot.audio
        if line.kind == "对白" and not line.cast
    )
    if unknown:
        notes.append(f"{unknown} 条声音的类型不认识")
    if voiceless:
        notes.append(f"{voiceless} 句对白没有说话人")
    if missed:
        notes.append(f"{missed} 行文字在原文里找不到")
    if moved:
        notes.append(f"后一镜删掉 {moved} 句挪过来的声音")
    if repeated:
        notes.append(f"{repeated} 处相邻两镜的旁白一样")
    return notes


# Take the cast of a shot from the people named in its panels, when all of
# them were named. A shot that covers a page nobody re-read keeps the
# cast the model gave it.
def _fill_cast(
    shots: list[Shot],
    people: BookPeople,
    cast_book: BookCast,
) -> None:
    named = {(panel.page, panel.panel): panel for panel in people.panels}
    order = [member.id for member in cast_book.cast]
    for shot in shots:
        found: list[str] = []
        complete = True
        for panel in shot.panels:
            record = named.get((panel.page, panel.panel))
            if record is None:
                complete = False
                break
            for person in record.people:
                if person.cast not in found:
                    found.append(person.cast)
        if complete:
            shot.cast = [cast_id for cast_id in order if cast_id in found]


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
    parsed = BookScenes.from_dict({"scenes": entries})
    return parsed.scenes, keys


# One panel is one reference image, and the service takes nine images in one
# request, so a shot keeps few panels and leaves room for the cast crops and
# the place master.
MAX_PANELS = 4

# The two kinds a person says. A shot whose picture carries no words may
# hold either of them, but never a sound effect, which has to be printed.
SPOKEN = ("旁白", "对白")

# Characters that carry a number, which a rewrite must keep.
NUMERALS = set("零一二三四五六七八九十百千万亿0123456789")


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
        covered = _covered(entry, panels, notes)
        if not covered:
            continue
        cast = [
            cast_id
            for cast_id in _texts(entry.get("cast"))
            if cast_id in cast_ids
        ]
        beats = _texts(entry.get("beats"))
        lines = _audio(entry.get("audio"), cast_ids)
        for group, group_lines in _groups(
            _packed(_pages(covered)), lines, panels
        ):
            entries.append(
                {
                    "id": f"j{len(entries) + 1}",
                    "scene": keys.get(
                        str(entry.get("scene") or "").strip(), ""
                    ),
                    "panels": group,
                    "cast": cast,
                    "join": str(entry.get("join") or "").strip(),
                    "camera": entry.get("camera"),
                    "beats": _beats_for(beats, covered, group),
                    "audio": group_lines,
                    "continuity": entry.get("continuity"),
                }
            )
    parsed = BookShots.from_dict({"shots": entries})
    return parsed.shots, notes


# Return the panels of one shot page by page, in the order they are listed.
def _pages(covered: list[dict]) -> list[list[dict]]:
    pages: list[list[dict]] = []
    for item in covered:
        if pages and pages[-1][0]["page"] == item["page"]:
            pages[-1].append(item)
        else:
            pages.append([item])
    return pages


# Pack the pages of one action into clips, cutting only between pages.
def _packed(pages: list[list[dict]]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    group: list[dict] = []
    for page in pages:
        if group and len(group) + len(page) > MAX_PANELS:
            groups.append(group)
            group = []
        group = group + page
    return groups + [group] if group else groups


# Cut the panels of one action into clips the service can render.
def _groups(
    groups: list[list[dict]],
    lines: list[dict],
    panels: dict[tuple[str, int], object],
) -> list[tuple[list[dict], list[dict]]]:
    if len(groups) == 1:
        return [(groups[0], lines)]

    carried: list[list[dict]] = [[] for _ in groups]
    for line in lines:
        carried[_group_of(str(line.get("text") or ""), groups, panels)].append(
            line
        )
    return list(zip(groups, carried))


# Find the clip that shows the panel a line is printed on.
def _group_of(
    text: str,
    groups: list[list[dict]],
    panels: dict[tuple[str, int], object],
) -> int:
    wanted = "".join(char for char in text if not char.isspace())
    if not wanted:
        return 0
    for number, group in enumerate(groups):
        for item in group:
            source = getattr(panels[(item["page"], item["panel"])], "text", "")
            squeezed = "".join(char for char in source if not char.isspace())
            if wanted in squeezed:
                return number
    return 0


# Give a clip the beats that belong to its own panels.
def _beats_for(
    beats: list[str],
    covered: list[dict],
    group: list[dict],
) -> list[str]:
    if len(group) == len(covered) or not covered:
        return beats
    mine = [item for item in group if item in covered]
    if len(beats) == len(covered):
        return [beats[covered.index(item)] for item in mine]
    start = covered.index(mine[0]) if mine else 0
    size = len(beats) / len(covered)
    first = round(start * size)
    last = round((start + len(group)) * size)
    return beats[first:last]


# Keep the panels a shot really covers, in the order the shot lists them.
def _covered(
    entry: dict,
    panels: dict[tuple[str, int], object],
    notes: list[str],
) -> list[dict]:
    kept = []
    for item in entry.get("panels") or []:
        if not isinstance(item, dict):
            continue
        page_name = str(item.get("page") or "").strip()
        index = _int(item.get("panel"))
        if (page_name, index) not in panels:
            notes.append(f"{page_name} 第 {index} 块不存在")
            continue
        kept.append({"page": page_name, "panel": index})
    return kept


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


# Join the lines of one speaker that sit next to each other in a shot.
def _merge(shots: list[Shot]) -> None:
    for shot in shots:
        merged: list = []
        for line in shot.audio:
            last = merged[-1] if merged else None
            if (
                last is not None
                and line.kind != "音效"
                and last.kind == line.kind
                and last.cast == line.cast
            ):
                last.text = _seam(last.text, line.text)
                continue
            merged.append(line)
        shot.audio = merged


# Put two printed pieces back together without leaving a gap.
def _seam(first: str, second: str) -> str:
    return first.rstrip() + second.lstrip()


# Fill the spoken text of every line, rewriting the narration.
def _spoken(
    shots: list[Shot],
    cast_book: BookCast,
    llm: LLMClient,
    cache: Cache | None,
    book_id: str,
    pages: list[PageContent],
) -> list[str]:
    for shot in shots:
        for line in shot.audio:
            line.spoken = _clean(line.text)

    sound = any(
        line.kind in ("旁白", "音效") for shot in shots for line in shot.audio
    )
    if not sound:
        return []

    prompt = spoken_prompt(shots, pages)
    try:
        fields = _ask(llm, prompt, [], cache, book_id, "spoken")
    except (LLMError, ValueError) as exc:
        return [str(exc)]

    names = [member.name for member in cast_book.cast if member.name]
    wanted = {
        (shot.id, number): line
        for shot in shots
        for number, line in enumerate(shot.audio)
        if line.kind == "旁白"
    }
    notes = []
    for entry in fields.get("lines") or []:
        if not isinstance(entry, dict):
            continue
        shot_id = str(entry.get("shot") or "").strip()
        line = wanted.get((shot_id, _int(entry.get("index"))))
        if line is None:
            continue
        spoken = _clean(str(entry.get("spoken") or ""))
        if _keeps(line.text, spoken, names):
            line.spoken = spoken
        else:
            notes.append(f"{shot_id} 的旁白改写不合格，用了原句")
    return notes + _drop_sounds(shots, fields)


# Drop the sound effects the review could not explain from the picture.
def _drop_sounds(shots: list[Shot], fields: dict) -> list[str]:
    dropped = set()
    for entry in fields.get("sounds") or []:
        if not isinstance(entry, dict) or entry.get("keep", True):
            continue
        shot_id = str(entry.get("shot") or "").strip()
        dropped.add((shot_id, _int(entry.get("index"))))
    if not dropped:
        return []

    removed = 0
    for shot in shots:
        kept = []
        for number, line in enumerate(shot.audio):
            if line.kind == "音效" and (shot.id, number) in dropped:
                removed += 1
                continue
            kept.append(line)
        shot.audio = kept
    return [f"去掉 {removed} 条说不通的音效"] if removed else []


# Return the text as it should be read aloud.
def _clean(text: str) -> str:
    for mark in "“”『』「」":
        text = text.replace(mark, "")
    return _tight(" ".join(text.split()))


# Drop the spaces that sit between two Chinese characters.
def _tight(text: str) -> str:
    kept = []
    for index, char in enumerate(text):
        between = 0 < index < len(text) - 1
        if (
            char == " "
            and between
            and _chinese(text[index - 1])
            and _chinese(text[index + 1])
        ):
            continue
        kept.append(char)
    return "".join(kept)


# Tell whether one character is Chinese, punctuation included.
def _chinese(char: str) -> bool:
    return (
        "\u3000" <= char <= "\u303f"
        or "\u4e00" <= char <= "\u9fff"
        or "\uff00" <= char <= "\uffef"
    )


# Tell whether a rewrite keeps the facts the page states.
def _keeps(original: str, rewritten: str, names: list[str]) -> bool:
    if not rewritten.strip():
        return False
    share = len(rewritten) / max(1, len(original))
    if not 0.7 <= share <= 1.3:
        return False
    if _numerals(original) != _numerals(rewritten):
        return False
    return all(name in rewritten for name in names if name in original)


# Return the counting words of a text, sorted for comparison.
def _numerals(text: str) -> list[str]:
    return sorted(char for char in text if char in NUMERALS)


# Match every sound back to the printed text, so nothing is paraphrased. A
# shot whose panels carry no printed text may hold a written line, and the
# shot after it then loses the line that was taken over. Two shots in a row
# that still say the same narration are counted.
def _printed(shots: list[Shot], panels: dict) -> tuple[int, int, int]:
    missed = 0
    bare = []
    for shot in shots:
        sources = [
            getattr(panels.get((item.page, item.panel)), "text", "") or ""
            for item in shot.panels
        ]
        bare.append(not any(source.strip() for source in sources))
        for line in shot.audio:
            exact = next(
                (
                    found
                    for source in sources
                    if (found := _as_printed(line.text, source)) is not None
                ),
                None,
            )
            if exact is not None:
                line.text = exact
            elif line.kind not in SPOKEN or not bare[-1]:
                missed += 1

    moved = _taken(shots, bare)
    repeated = 0
    for number in range(1, len(shots)):
        said = _squeeze(_narration(shots[number - 1]))
        if said and said == _squeeze(_narration(shots[number])):
            repeated += 1
    return missed, repeated, moved


# Drop the sound a shot took over from the shot after it, unless that shot
# would be left with nothing to say.
def _taken(shots: list[Shot], bare: list[bool]) -> int:
    dropped = 0
    for number in range(1, len(shots)):
        now = shots[number]
        if not bare[number - 1] or len(now.audio) < 2:
            continue
        said = {_squeeze(line.text) for line in shots[number - 1].audio}
        kept = [line for line in now.audio if _squeeze(line.text) not in said]
        dropped += len(now.audio) - len(kept)
        now.audio = kept
    return dropped


# Join the narration of one shot into a single string for comparison.
def _narration(shot: Shot) -> str:
    return "".join(line.text for line in shot.audio if line.kind == "旁白")


# Drop every space, so two spellings of the same line compare equal.
def _squeeze(text: str) -> str:
    return "".join(char for char in text if not char.isspace())


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
