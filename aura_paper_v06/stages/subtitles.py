"""Place every spoken line on the finished film as a subtitle file."""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..media import audio, ffmpeg
from ..schema.compose import BookCompose, ComposedShot
from ..schema.job import BookJobs, JobLine
from ..schema.subtitles import BookSubtitles
from ..schema.voice import BookVoice
from ..store.output import write_json
from .paths import book_dir, shots_dir

# The subtitle file the film is burnt with, the reader's copy, and the
# burnt copy's suffix.
ASS_SUFFIX = ".ass"
VTT_SUFFIX = ".vtt"
BURN_SUFFIX = "-subs.mp4"

# Font families, as the files in resources/fonts name themselves.
NARRATOR_FONT = "Noto Serif SC"
CAST_FONT = "ZCOOL KuaiLe"

# Colours are written as RGB here and turned round for ASS below.
NARRATOR_COLOUR = "F2EDE4"
CAST_COLOURS = (
    "E85D75",
    "2F7FD1",
    "E09B2D",
    "6C4AB6",
    "2E8B57",
    "C2185B",
)

# The lines the film carries, and how they sit on the picture.
NARRATOR = "旁白"
SPOKEN = (NARRATOR, "对白")
NARRATOR_SIZE = 32
CAST_SIZE = 32
OUTLINE = 2
SHADOW = 1
MARGIN_VERTICAL = 40
MARGIN_SIDE = 120
OUTLINE_COLOUR = "101010"

# Marks that never take a space in front of them.
PUNCTUATION = "，。、；：！？…,.!?;:"


@dataclass
class Cue:
    """One spoken line, in seconds from the start of the film."""

    start: float
    end: float
    style: str
    text: str


@dataclass
class Style:
    """One way a line looks."""

    name: str
    font: str
    size: int
    colour: str


def subtitles(
    book_id: str,
    *,
    root: str | Path | None = None,
    fonts: str | Path | None = None,
    burn: bool = False,
) -> BookSubtitles:
    """Read jobs.json and compose.json, write subtitles.ass and .vtt."""
    directory = book_dir(book_id, root)
    result = BookSubtitles(id=book_id)
    book = _read_compose(directory)
    film = directory / book.film if book.film else None
    if film is None or not film.is_file():
        result.error = "整片还没拼，先跑 run_compose.py"
        write_json(book_id, "subtitles", result.to_dict(), root)
        return result

    jobs = _read_book(directory)
    takes = {shot.shot: shot for shot in book.shots}
    spoken = _read_spoken(directory)
    styles = _styles(jobs)
    cues = _cues(jobs, takes, spoken, directory)
    if not cues:
        result.error = "没有可以上字幕的台词"
        write_json(book_id, "subtitles", result.to_dict(), root)
        return result

    path = directory / f"subtitles{ASS_SUFFIX}"
    path.write_text(_ass(cues, styles, ffmpeg.probe(film)), encoding="utf-8")
    result.file = path.name
    result.vtt = f"subtitles{VTT_SUFFIX}"
    (directory / result.vtt).write_text(_vtt(cues), encoding="utf-8")
    result.cues = len(cues)

    if burn:
        result.burned, result.error = _burn(
            film, path, fonts, shots_dir(book_id, root)
        )
    write_json(book_id, "subtitles", result.to_dict(), root)
    return result


# Read the record of the finished film, or an empty one this stage waits on.
def _read_compose(directory: Path) -> BookCompose:
    path = directory / "compose.json"
    if not path.is_file():
        return BookCompose()
    return BookCompose.from_dict(json.loads(path.read_text("utf-8")))


# Read the lines the jobs stage placed inside every shot.
def _read_book(directory: Path) -> BookJobs:
    path = directory / "jobs.json"
    if not path.is_file():
        return BookJobs()
    return BookJobs.from_dict(json.loads(path.read_text("utf-8")))


# Read the wording each line was spoken with, keyed by shot and index.
def _read_spoken(directory: Path) -> dict[tuple[str, int], str]:
    path = directory / "voice.json"
    if not path.is_file():
        return {}
    book = BookVoice.from_dict(json.loads(path.read_text("utf-8")))
    return {
        (shot.shot, line.index): line.spoken
        for shot in book.shots
        for line in shot.lines
        if line.spoken
    }


# Put every spoken line at its place in the film. Narration reads the
# wording it was spoken with, because that is what the viewer hears.
def _cues(
    jobs: BookJobs,
    takes: dict[str, ComposedShot],
    spoken: dict[tuple[str, int], str],
    directory: Path,
) -> list[Cue]:
    cues = []
    for job in jobs.shots:
        take = takes.get(job.shot)
        if take is None or not take.seconds:
            continue
        first = len(cues)
        for line in job.lines:
            if line.kind not in SPOKEN:
                continue
            text = _line_text(job.shot, line, spoken)
            if not text:
                continue
            start = take.start + line.start_ms / 1000
            end = min(
                start + line.duration_ms / 1000, take.start + take.seconds
            )
            if end <= start:
                continue
            style = NARRATOR if line.kind == NARRATOR else line.cast
            cues.append(Cue(start, end, style, text))
        _hold(cues, first, take, _heard(take, directory))
    return cues


# Keep each line on screen until the next one starts, and the last line of
# a shot until the take really stops speaking. The model lands up to two
# seconds after the track it was sent.
def _hold(
    cues: list[Cue],
    first: int,
    take: ComposedShot,
    said_end: float,
) -> None:
    if first >= len(cues):
        return
    stop = take.start + take.seconds
    for index in range(first, len(cues) - 1):
        following = cues[index + 1].start
        cues[index].end = min(stop, max(cues[index].end, following))
    last = cues[-1]
    last.end = min(stop, max(last.end, said_end))


# Find when the sound of one take stops, in film seconds. A take without
# sound of its own reports nothing.
def _heard(take: ComposedShot, directory: Path) -> float:
    path = directory / take.file if take.file else None
    if path is None or not path.is_file():
        return 0.0
    with tempfile.TemporaryDirectory() as folder:
        heard = Path(folder) / "heard.wav"
        try:
            audio.extract(path, heard)
            quiet = audio.silence_at_end(heard)
        except ffmpeg.FFmpegError:
            return 0.0
    length = ffmpeg.probe(path).duration_ms / 1000
    return take.start + max(0.0, length - quiet)


# Read the words a line puts on screen.
def _line_text(
    shot: str,
    line: JobLine,
    spoken: dict[tuple[str, int], str],
) -> str:
    if line.kind == NARRATOR:
        return spoken.get((shot, line.index), "").strip() or line.text.strip()
    return line.text.strip()


# Give the narrator and every character a look of its own.
def _styles(jobs: BookJobs) -> list[Style]:
    order = []
    for job in jobs.shots:
        for line in job.lines:
            if line.kind != NARRATOR and line.cast and line.cast not in order:
                order.append(line.cast)
    styles = [Style(NARRATOR, NARRATOR_FONT, NARRATOR_SIZE, NARRATOR_COLOUR)]
    for index, cast in enumerate(order):
        colour = CAST_COLOURS[index % len(CAST_COLOURS)]
        styles.append(Style(cast, CAST_FONT, CAST_SIZE, colour))
    return styles


# Write the ASS file: one style line per look, one event per line.
def _ass(cues: list[Cue], styles: list[Style], info: ffmpeg.MediaInfo) -> str:
    parts = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {info.width or 1280}",
        f"PlayResY: {info.height or 720}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    for style in styles:
        parts.append(_style_line(style))
    parts += [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text",
    ]
    for cue in cues:
        text = cue.text.replace("\n", "\\N")
        parts.append(
            f"Dialogue: 0,{_clock(cue.start)},{_clock(cue.end)},"
            f"{cue.style},,0,0,0,,{text}"
        )
    return "\n".join(parts) + "\n"


# Write one style line, with the colours turned round for ASS.
def _style_line(style: Style) -> str:
    return (
        f"Style: {style.name},{style.font},{style.size},"
        f"{_colour(style.colour)},&H000000FF,"
        f"{_colour(OUTLINE_COLOUR)},&H64000000,"
        "0,0,0,0,100,100,0,0,1,"
        f"{OUTLINE},{SHADOW},2,"
        f"{MARGIN_SIDE},{MARGIN_SIDE},{MARGIN_VERTICAL},1"
    )


# Turn an RGB hex string into the BGR order ASS reads.
def _colour(rgb: str) -> str:
    return f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


# Write a time the way ASS reads it, to the hundredth of a second.
def _clock(seconds: float) -> str:
    total = max(0, round(seconds * 100))
    hours, rest = divmod(total, 360000)
    minutes, rest = divmod(rest, 6000)
    secs, cents = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cents:02d}"


# Write the WebVTT file the reader loads: one cue per line, the speaker as
# a voice span so the page can style it.
def _vtt(cues: list[Cue]) -> str:
    parts = ["WEBVTT", ""]
    for cue in cues:
        parts.append(f"{_vtt_clock(cue.start)} --> {_vtt_clock(cue.end)}")
        parts.append(f"<v {cue.style}>{_markup(_flat(cue.text))}</v>")
        parts.append("")
    return "\n".join(parts)


# Join the printed line breaks into one line. A break between two Latin
# words keeps a space, one beside punctuation or between two Chinese
# characters keeps none.
def _flat(text: str) -> str:
    joined = " ".join(text.split())
    joined = _sentence_space(joined)
    kept = []
    for index, char in enumerate(joined):
        if char == " " and 0 < index < len(joined) - 1:
            before = joined[index - 1]
            after = joined[index + 1]
            if after in PUNCTUATION:
                continue
            if _chinese(before) and _chinese(after):
                continue
        kept.append(char)
    return "".join(kept)


# Put a space back where a sentence mark ran straight into the next word.
def _sentence_space(text: str) -> str:
    return re.sub(r"(?<=[a-z)\"'’])([.?!])(?=[A-Z])", r"\1 ", text)


# Tell whether one character is Chinese, punctuation included.
def _chinese(char: str) -> bool:
    return (
        "\u3000" <= char <= "\u303f"
        or "\u4e00" <= char <= "\u9fff"
        or "\uff00" <= char <= "\uffef"
    )


# Turn the characters WebVTT reads as markup into plain text.
def _markup(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    return text.replace(">", "&gt;")


# Write a time the way WebVTT reads it, to the thousandth of a second.
def _vtt_clock(seconds: float) -> str:
    total = max(0, round(seconds * 1000))
    hours, rest = divmod(total, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


# Burn the subtitle file into a copy of the film, leaving the master alone.
def _burn(
    film: Path,
    ass: Path,
    fonts: str | Path | None,
    out_dir: Path,
) -> tuple[str, str]:
    folder = Path(fonts) if fonts is not None else _default_fonts()
    if not folder.is_dir():
        return "", f"找不到字体目录 {folder}，先跑 scripts/get_fonts.sh"
    target = out_dir / f"film{BURN_SUFFIX}"
    graph = f"ass=filename={ass}:fontsdir={folder}"
    try:
        ffmpeg.run(
            [
                ffmpeg.FFMPEG,
                *ffmpeg.COMMON,
                "-i",
                str(film),
                "-vf",
                graph,
                *ffmpeg.VIDEO_CODEC,
                "-crf",
                "18",
                "-preset",
                "medium",
                "-c:a",
                "copy",
                *ffmpeg.FASTSTART,
                str(target),
            ]
        )
    except ffmpeg.FFmpegError as exc:
        return "", f"字幕没烧上：{exc}"
    return f"shots/{target.name}", ""


# Where the font script puts the two families.
def _default_fonts() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "fonts"
