"""Turn every shot into a video generation job."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from PIL import Image

from ..media.image import load_image, save_jpeg
from ..output import write_json
from ..prompts import job_prompt
from ..schema.cast import BookCast, Cast
from ..schema.identify import BookPeople, PanelPeople
from ..schema.job import BookJobs, Job, JobImage, JobLine
from ..schema.location import BookLocations
from ..schema.shot import BookShots, Shot
from ..schema.voice import BookVoice, VoiceShot
from .paths import book_dir, jobs_dir, panel_name
from .voice import DEFAULT_GAP_MS

# The video service takes 4 to 15 whole seconds.
MIN_SECONDS = 4
MAX_SECONDS = 15

# Room after the last sound, so the picture does not stop with the voice.
TAIL_MS = 300

# A sound effect needs a moment on the timeline, though nothing is spoken.
SFX_MS = 600

# The service takes at most nine reference images in one request.
MAX_IMAGES = 9

# A reference image must be between 0.4 and 2.5 times as wide as it is tall.
MAX_ASPECT = 2.5
MIN_ASPECT = 0.4

# A padded copy is written once from an already encoded crop.
PAD_QUALITY = 95
PAD_COLOUR = (255, 255, 255)


def jobs(
    book_id: str,
    *,
    ratio: str,
    resolution: str,
    audio: bool,
    root: str | Path | None = None,
) -> BookJobs:
    """Read four artifacts, build one job per shot, write jobs.json."""
    directory = book_dir(book_id, root)
    shot_book = _read_shots(directory)
    voice_book = _read_voice(directory)
    cast_book = _read_cast(directory)
    places = _read_locations(directory)
    people = _read_people(directory)
    by_shot = {shot.shot: shot for shot in voice_book.shots}

    out_dir = jobs_dir(book_id, root)
    shutil.rmtree(out_dir, ignore_errors=True)

    result = BookJobs(id=book_id, ratio=ratio, resolution=resolution)
    for shot in shot_book.shots:
        spoken = by_shot.get(shot.id)
        lines = _lines(shot, spoken)
        result.shots.append(
            _build(
                shot=shot,
                spoken=spoken,
                style=shot_book.style,
                cast=_cast_of(shot, cast_book),
                place=_place(shot, places),
                places=places,
                people=people,
                lines=lines,
                ratio=ratio,
                resolution=resolution,
                audio=audio,
                directory=directory,
                out_dir=out_dir,
            )
        )

    result.error = "；".join(
        f"{job.shot}：{job.error}" for job in result.shots if job.error
    )
    write_json(book_id, "jobs", result.to_dict(), root)
    return result


# Fill one job from the shot and the artifacts around it.
def _build(
    *,
    shot: Shot,
    spoken: VoiceShot | None,
    style: str,
    cast: list[Cast],
    place: str,
    places: BookLocations,
    people: BookPeople,
    lines: list[JobLine],
    ratio: str,
    resolution: str,
    audio: bool,
    directory: Path,
    out_dir: Path,
) -> Job:
    job = Job(
        shot=shot.id,
        scene=shot.scene,
        location=place,
        join=shot.join,
        panels=list(shot.panels),
        ratio=ratio,
        resolution=resolution,
        audio=audio or any(line.kind == "音效" for line in shot.audio),
        lines=lines,
        audio_ms=_length(lines),
    )
    job.duration = _seconds(job.audio_ms)
    job.images = _images(
        job.shot, shot, cast, place, places, people, directory, out_dir
    )
    job.prompt = job_prompt(
        shot,
        style=style,
        place=_place_text(place, places),
        cast=cast,
        images=job.images,
        seconds=job.duration,
        audio=job.audio,
    )
    if len(job.images) > MAX_IMAGES:
        job.images = job.images[:MAX_IMAGES]
        job.error = _joined(
            job.error, f"参考图超过 {MAX_IMAGES} 张，只留前面几张"
        )
    wanted = sum(1 for line in shot.audio if line.kind != "音效")
    found = sum(1 for line in lines if line.kind != "音效")
    if found < wanted:
        job.error = _joined(
            job.error,
            f"配音少了 {wanted - found} 句，先重跑 run_voice.py",
        )
    if job.audio_ms + TAIL_MS > MAX_SECONDS * 1000:
        job.error = _joined(
            job.error,
            f"音轨 {job.audio_ms / 1000:.1f} 秒，超过 {MAX_SECONDS} 秒上限",
        )
    return job


# Place every sound of the shot on its timeline, leaving a gap between them.
def _lines(shot: Shot, spoken: VoiceShot | None) -> list[JobLine]:
    gap = spoken.gap_ms if spoken else DEFAULT_GAP_MS
    records = {line.index: line for line in spoken.lines} if spoken else {}
    lines = []
    for index, sound in enumerate(shot.audio):
        if sound.kind == "音效":
            lines.append(
                JobLine(
                    index=index,
                    kind=sound.kind,
                    cast=sound.cast,
                    text=sound.text,
                    duration_ms=SFX_MS,
                )
            )
            continue
        record = records.get(index)
        if record is None:
            continue
        lines.append(
            JobLine(
                index=index,
                kind=sound.kind,
                cast=sound.cast,
                text=sound.text,
                file=record.file,
                duration_ms=record.duration_ms,
            )
        )

    at = 0
    for number, line in enumerate(lines):
        if number:
            at += gap
        line.start_ms = at
        at += line.duration_ms
    return lines


# Return how long the sound of a shot runs.
def _length(lines: list[JobLine]) -> int:
    if not lines:
        return 0
    return lines[-1].start_ms + lines[-1].duration_ms


# Round the sound up to whole seconds the service accepts.
def _seconds(audio_ms: int) -> int:
    seconds = math.ceil((audio_ms + TAIL_MS) / 1000)
    return min(MAX_SECONDS, max(MIN_SECONDS, seconds))


# Return the place of a shot, taken from the first panel that has one.
def _place(shot: Shot, places: BookLocations) -> str:
    for panel in shot.panels:
        for item in places.panel_locations:
            if item.page == panel.page and item.panel == panel.panel:
                return item.location
    return ""


# Say what the place looks like, for the prompt.
def _place_text(place: str, places: BookLocations) -> str:
    for location in places.locations:
        if location.id == place:
            parts = (location.name, location.light)
            return "，".join(part for part in parts if part)
    return place


# Pick the characters of the shot, in the order the cast lists them.
def _cast_of(shot: Shot, cast_book: BookCast) -> list[Cast]:
    return [member for member in cast_book.cast if member.id in shot.cast]


# List the images for one job: every panel, one crop per character, the place.
def _images(
    name: str,
    shot: Shot,
    cast: list[Cast],
    place: str,
    places: BookLocations,
    people: BookPeople,
    directory: Path,
    out_dir: Path,
) -> list[JobImage]:
    images = []
    seen: set[Path] = set()
    named = {(panel.page, panel.panel): panel for panel in people.panels}
    names = {member.id: member.name or member.id for member in cast}
    folder = directory / "panels"
    for number, panel in enumerate(shot.panels, start=1):
        crop = folder / panel_name(panel.page, panel.panel)
        if not crop.is_file() or crop in seen:
            continue
        seen.add(crop)
        people_text = _people_text(named.get((panel.page, panel.panel)), names)
        images.append(
            JobImage(
                file=_fitted(crop, out_dir, f"{name}-{number}", directory),
                note=f"第 {number} 格分镜{people_text}",
            )
        )

    figures = directory / "figures"
    for member in cast:
        crop = _first_existing(figures, member.pictures)
        if crop is None or crop in seen:
            continue
        seen.add(crop)
        images.append(
            JobImage(
                file=_fitted(crop, out_dir, f"{name}-{member.id}", directory),
                note=f"角色 {member.name or member.id} 的参考图，{member.look}",
            )
        )

    master = _master(place, places, directory)
    if master is not None and master not in seen:
        images.append(
            JobImage(
                file=_fitted(master, out_dir, f"{name}-place", directory),
                note=f"场地 {place} 的母图，只用来定环境和光",
            )
        )
    return images


# Say who a panel shows, when somebody took a closer look at it.
def _people_text(
    record: PanelPeople | None,
    names: dict[str, str],
) -> str:
    if record is None or not record.people:
        return ""
    said = "；".join(
        f"{names.get(person.cast, person.cast)} {person.parts}"
        for person in record.people
    )
    return f"（{said}）"


# Return the first crop of a character that is still on disk.
def _first_existing(folder: Path, names: list[str]) -> Path | None:
    for name in names:
        path = folder / name
        if path.is_file():
            return path
    return None


# Return the master crop of one place, when it is still on disk.
def _master(
    place: str,
    places: BookLocations,
    directory: Path,
) -> Path | None:
    if not place:
        return None
    for location in places.locations:
        if location.id != place or not location.master:
            continue
        path = directory / "panels" / location.master
        if path.is_file():
            return path
    return None


# Return the file to send, padding a crop the service cannot take as is.
def _fitted(path: Path, out_dir: Path, name: str, directory: Path) -> str:
    image = load_image(path)
    width, height = image.size
    if MIN_ASPECT <= width / height <= MAX_ASPECT:
        return _relative(path, directory)
    padded = out_dir / f"{name}.jpg"
    save_jpeg(_pad(image), padded, PAD_QUALITY)
    return _relative(padded, directory)


# Add white bars until the picture fits the aspect limits of the service.
def _pad(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width / height > MAX_ASPECT:
        target = math.ceil(width / MAX_ASPECT)
        canvas = Image.new(image.mode, (width, target), PAD_COLOUR)
        canvas.paste(image, (0, (target - height) // 2))
        return canvas
    target = math.ceil(height * MIN_ASPECT)
    canvas = Image.new(image.mode, (target, height), PAD_COLOUR)
    canvas.paste(image, ((target - width) // 2, 0))
    return canvas


# Return the path of one file inside the book folder.
def _relative(path: Path, directory: Path) -> str:
    return path.relative_to(directory).as_posix()


# Join two notes into the error text of a job.
def _joined(error: str, note: str) -> str:
    return "；".join(part for part in (error, note) if part)


# Read the storyboard's record of the shots.
def _read_shots(directory: Path) -> BookShots:
    path = directory / "shots.json"
    return BookShots.from_dict(json.loads(path.read_text("utf-8")))


# Read the voice stage's record of the spoken audio.
def _read_voice(directory: Path) -> BookVoice:
    path = directory / "voice.json"
    return BookVoice.from_dict(json.loads(path.read_text("utf-8")))


# Read the cast stage's record of the characters.
def _read_cast(directory: Path) -> BookCast:
    path = directory / "cast.json"
    return BookCast.from_dict(json.loads(path.read_text("utf-8")))


# Read the assets stage's record of the places.
def _read_locations(directory: Path) -> BookLocations:
    path = directory / "locations.json"
    return BookLocations.from_dict(json.loads(path.read_text("utf-8")))


# Read the identify stage's record of the people, when it was run.
def _read_people(directory: Path) -> BookPeople:
    path = directory / "identify.json"
    if not path.is_file():
        return BookPeople()
    return BookPeople.from_dict(json.loads(path.read_text("utf-8")))
