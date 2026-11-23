"""Lay the spoken lines under every rendered clip and mix them together."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

from ..clients.tts import DEFAULT_RATE, TTSClient, TTSError
from ..media import audio, ffmpeg
from ..media.image import extend_sides, load_image, save_jpeg
from ..schema.compose import BookCompose, ComposedJoin, ComposedShot
from ..schema.content import BookContent
from ..schema.job import BookJobs, Job
from ..schema.voice import NARRATOR, BookVoice
from ..store.cache import Cache, fingerprint
from ..store.output import write_json
from .paths import book_dir, shots_dir

# 16-bit mono, so one second holds rate * 2 bytes.
BYTES_PER_FRAME = 2

# The speech client writes a plain header in front of its samples.
WAV_HEADER = 44

# How loud the sound a clip carries sits under the local track.
BACKGROUND_VOLUME = ffmpeg.BACKGROUND_VOLUME

# Every take is encoded the same way, so the takes can be joined later.
SUFFIX = ".mp4"
TRACK_SUFFIX = ".wav"
HEARD_SUFFIX = "-heard.wav"

# A clip that speaks this long inside the silence it was sent is reported.
UNASKED_SECONDS = 0.3

# How long two shots share the screen when they dissolve into each other.
OVERLAP = 0.5

# How long a take holds its last picture after the clip ends. The hold is
# the room a dissolve shares, so no word ever sits inside that stretch.
HOLD = 0.5

# The title is read slower than the story, with room to breathe either side.
TITLE_SPEED = 0.8
TITLE_LEAD_MS = 1500
TITLE_TAIL_MS = 1000

# How long the card takes to appear and to leave.
TITLE_FADE = 0.4

# What the card and its track are called.
TITLE_CARD = "title_card"

# The card image is written as JPEG, like the pages.
IMAGE_SUFFIX = ".jpg"
CARD_QUALITY = 95

# How much the mirrored edge filling is blurred behind the page. The
# page's own watermark reaches its edges, so the filling is softened
# until that text no longer reads backwards.
CARD_SOFTEN = 40

# A shot with no clip yet is expected while the render is still running.
MISSING = "还没有生成这一镜"

# The frames either side of a join are compared at this size.
JUMP_BOX = (64, 64)


def compose(
    book_id: str,
    *,
    only: str = "",
    tts: TTSClient | None = None,
    root: str | Path | None = None,
    cache: Cache | None = None,
) -> BookCompose:
    """Read jobs.json, mix one take per shot, write compose.json."""
    directory = book_dir(book_id, root)
    job_book = _read_jobs(directory)
    out_dir = shots_dir(book_id, root)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = BookCompose(id=book_id)
    for job in job_book.shots:
        if only and job.shot != only:
            continue
        result.shots.append(_one(job, directory, out_dir))

    result.joins = _joins(job_book.shots, result.shots, out_dir)
    notes = []
    if not only:
        _film(
            book_id,
            job_book.shots,
            result,
            notes,
            directory,
            out_dir,
            root,
            tts,
            cache,
        )
    result.error = "；".join(
        [
            f"{shot.shot}：{shot.error}"
            for shot in result.shots
            if shot.error and shot.error != MISSING
        ]
        + notes
    )
    write_json(book_id, "compose", result.to_dict(), root)
    return result


def title_card(
    book_id: str,
    *,
    tts: TTSClient,
    size: tuple[int, int],
    root: str | Path | None = None,
    cache: Cache | None = None,
    speed: float = TITLE_SPEED,
    lead_ms: int = TITLE_LEAD_MS,
    tail_ms: int = TITLE_TAIL_MS,
) -> str:
    """Speak the cover title and put it on a card built from the cover.

    The card lasts as long as the spoken title plus the silence before
    and after it, so the words never crowd the edges.
    """
    directory = book_dir(book_id, root)
    content = _read_content(directory)
    title = content.title.strip()
    cover = content.cover_page
    if not title:
        raise ValueError("封面没有书名")
    if cover is None:
        raise ValueError("还没有封面图")

    voice_id = _voice_for(directory, "旁白", NARRATOR)
    out_dir = shots_dir(book_id, root)
    out_dir.mkdir(parents=True, exist_ok=True)

    speech = out_dir / f"{TITLE_CARD}_speech{TRACK_SUFFIX}"
    _speak_title(title, voice_id, speed, speech, tts, cache)
    seconds = (lead_ms + _file_ms(speech) + tail_ms) / 1000
    track = out_dir / f"{TITLE_CARD}{TRACK_SUFFIX}"
    _pad_speech(track, speech, lead_ms, tail_ms)
    speech.unlink(missing_ok=True)

    image = out_dir / f"{TITLE_CARD}{IMAGE_SUFFIX}"
    still = load_image(directory / "pages" / cover.filename)
    save_jpeg(
        extend_sides(still, size, soften=CARD_SOFTEN),
        image,
        CARD_QUALITY,
    )

    target = out_dir / f"{TITLE_CARD}{SUFFIX}"
    ffmpeg.title_card(
        image,
        track,
        target,
        size=size,
        seconds=seconds,
        fade=TITLE_FADE,
    )
    return f"shots/{target.name}"


# Speak the title, reusing the cached audio when nothing changed.
def _speak_title(
    text: str,
    voice_id: str,
    speed: float,
    target: Path,
    tts: TTSClient,
    cache: Cache | None,
) -> None:
    key = fingerprint(text, voice_id, speed, *tts.signature)
    if cache is not None and cache.enabled:
        cached = cache.file_path("voice", key, TRACK_SUFFIX)
        if cached.is_file():
            target.write_bytes(cached.read_bytes())
            return

    tts.synthesize(text, voice=voice_id, speed=speed).save(target)
    if cache is not None and cache.enabled:
        cached = cache.file_path("voice", key, TRACK_SUFFIX)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(target.read_bytes())


# Put the lead and tail silence around the spoken title.
def _pad_speech(
    target: Path,
    speech: Path,
    lead_ms: int,
    tail_ms: int,
) -> None:
    seconds = (lead_ms + _file_ms(speech) + tail_ms) / 1000
    audio.write_track(target, [(lead_ms, speech)], seconds)


# Return how long a WAV the speech client wrote lasts, in milliseconds.
def _file_ms(path: Path) -> int:
    size = max(0, path.stat().st_size - WAV_HEADER)
    return round(size * 1000 / (DEFAULT_RATE * BYTES_PER_FRAME))


# Read the understand stage's record of the book.
def _read_content(directory: Path) -> BookContent:
    path = directory / "understand.json"
    return BookContent.from_dict(json.loads(path.read_text("utf-8")))


# Return the voice of one speaker, using the fallback when it is unset.
def _voice_for(directory: Path, speaker: str, fallback: str) -> str:
    path = directory / "voice.json"
    if not path.is_file():
        return fallback
    book = BookVoice.from_dict(json.loads(path.read_text("utf-8")))
    return book.voices.get(speaker) or fallback


# Mix one shot, or record why it could not be done.
def _one(
    job: Job,
    directory: Path,
    out_dir: Path,
) -> ComposedShot:
    record = ComposedShot(shot=job.shot)
    source = f"clips/{job.shot}{SUFFIX}"
    clip = directory / source
    if not clip.is_file():
        record.error = MISSING
        return record

    record.source = source
    try:
        info = ffmpeg.probe(clip)
    except ffmpeg.FFmpegError as exc:
        record.error = str(exc)
        return record
    record.sound = info.has_audio

    seconds = round(_seconds(info) + HOLD, 3)
    track = out_dir / f"{job.shot}{TRACK_SUFFIX}"
    audio.write_track(track, _parts(job, directory), seconds)
    record.audio = f"shots/{track.name}"

    target = out_dir / f"{job.shot}{SUFFIX}"
    try:
        if info.has_audio:
            # A clip that speaks the dialogue must not be turned down, since
            # the track under it only carries the narration.
            level = 1.0 if job.reference else BACKGROUND_VOLUME
            ffmpeg.mix(
                clip,
                track,
                target,
                seconds=seconds,
                background=level,
                hold=HOLD,
            )
        else:
            ffmpeg.mux(clip, track, target, seconds=seconds, hold=HOLD)
    except ffmpeg.FFmpegError as exc:
        record.error = str(exc)
        return record

    record.file = f"shots/{target.name}"
    record.seconds = round(seconds, 3)
    if job.reference and info.has_audio:
        found = _narration_sound(job, clip, out_dir)
        if found >= UNASKED_SECONDS:
            record.error = f"旁白时段画面有声音 {found:.1f}s"
    return record


# Say how much the clip speaks inside the stretches that hold no words.
def _narration_sound(job: Job, clip: Path, out_dir: Path) -> float:
    windows = [
        (line.start_ms, line.start_ms + line.duration_ms)
        for line in job.lines
        if line.kind == "旁白" and line.duration_ms
    ]
    if not windows:
        return 0.0
    heard = out_dir / f"{job.shot}{HEARD_SUFFIX}"
    try:
        audio.extract(clip, heard)
    except ffmpeg.FFmpegError:
        return 0.0
    try:
        return audio.sound_in_windows(heard, windows)
    finally:
        heard.unlink(missing_ok=True)


# Take the shot at the whole length of its clip, cut to a whole number of
# frames so its picture and its sound end on the same frame.
def _seconds(info: ffmpeg.MediaInfo) -> float:
    length = info.video_ms or info.duration_ms
    frames = int(length * ffmpeg.FILM_FPS / 1000 + 1e-6)
    return round(frames / ffmpeg.FILM_FPS, 3)


# List the lines the local track has to carry. A shot that was sent a
# reference track lets the clip speak its dialogue, so those lines stay out.
def _parts(
    job: Job,
    directory: Path,
) -> list[tuple[int, Path]]:
    return [
        (line.start_ms, directory / line.file)
        for line in job.lines
        if line.file and not (job.reference and line.kind == "对白")
    ]


# Return a silent stretch of the given length.
def _silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(DEFAULT_RATE * seconds)


# Measure every join between two takes that are both on disk.
def _joins(
    jobs: list[Job],
    takes: list[ComposedShot],
    out_dir: Path,
) -> list[ComposedJoin]:
    found = {take.shot: take for take in takes if take.file}
    joins = []
    for number, job in enumerate(jobs[:-1]):
        after = jobs[number + 1]
        if job.shot not in found or after.shot not in found:
            continue
        joins.append(
            ComposedJoin(
                before=job.shot,
                after=after.shot,
                kind=after.join,
                jump=round(
                    _jump(
                        out_dir / f"{job.shot}{SUFFIX}",
                        out_dir / f"{after.shot}{SUFFIX}",
                        out_dir,
                    ),
                    1,
                ),
            )
        )
    return joins


# Compare the last picture of one take with the first of the next.
def _jump(before: Path, after: Path, folder: Path) -> float:
    first = ffmpeg.frame(before, folder / "tail.jpg", last=True)
    second = ffmpeg.frame(after, folder / "head.jpg")
    left = Image.open(first).convert("L").resize(JUMP_BOX)
    right = Image.open(second).convert("L").resize(JUMP_BOX)
    data = ImageChops.difference(left, right).tobytes()
    return sum(data) / len(data)


# Join every take into one film, once all of them are on disk.
def _film(
    book_id: str,
    jobs: list[Job],
    result: BookCompose,
    notes: list[str],
    directory: Path,
    out_dir: Path,
    root: str | Path | None,
    tts: TTSClient | None,
    cache: Cache | None,
) -> None:
    takes = [take for take in result.shots if take.file]
    if len(takes) != len(jobs):
        notes.append(f"还有 {len(jobs) - len(takes)} 镜没出片，先不拼整片")
        return
    if not takes:
        return

    paths = [out_dir / f"{job.shot}{SUFFIX}" for job in jobs]
    overlaps = [OVERLAP if job.join == "叠化" else 0.0 for job in jobs[1:]]
    card = _card(book_id, paths[0], root, notes, tts, cache)
    if card:
        paths = [directory / card] + paths
        overlaps = [OVERLAP] + overlaps
        result.title_card = card
    target = out_dir / f"film{SUFFIX}"
    try:
        ffmpeg.join(paths, target, overlaps=overlaps)
    except ffmpeg.FFmpegError as exc:
        notes.append(f"整片拼接失败：{exc}")
        return
    result.film = f"shots/{target.name}"
    result.seconds = round(ffmpeg.probe(target).duration_ms / 1000, 2)


# Build the title card, or note why it was left out.
def _card(
    book_id: str,
    first: Path,
    root: str | Path | None,
    notes: list[str],
    tts: TTSClient | None,
    cache: Cache | None,
) -> str:
    if tts is None:
        return ""
    try:
        return title_card(
            book_id,
            tts=tts,
            size=_frame_size(first),
            root=root,
            cache=cache,
        )
    except (TTSError, ffmpeg.FFmpegError, ValueError, OSError) as exc:
        notes.append(f"片头没做成：{exc}")
        return ""


# Return the size the film uses, read off its first take.
def _frame_size(path: Path) -> tuple[int, int]:
    info = ffmpeg.probe(path)
    return info.width, info.height


# Read the jobs stage's record of the shots.
def _read_jobs(directory: Path) -> BookJobs:
    path = directory / "jobs.json"
    return BookJobs.from_dict(json.loads(path.read_text("utf-8")))
