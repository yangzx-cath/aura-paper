"""Call ffmpeg and ffprobe for the video stages."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# ffmpeg asks before overwriting; the stages always mean to overwrite.
COMMON = ("-hide_banner", "-loglevel", "error", "-y")

# Encoding every stage produces, so clips join without a re-encode.
VIDEO_CODEC = ("-c:v", "libx264", "-pix_fmt", "yuv420p")
AUDIO_CODEC = ("-c:a", "aac", "-ar", "48000", "-ac", "2")
FASTSTART = ("-movflags", "+faststart")

# Every clip in the film runs at this frame rate.
FILM_FPS = 24

# How much of a failing call's output is worth keeping in the error.
ERROR_TAIL = 400

# The sound a clip comes with is usually the effect itself, not music.
BACKGROUND_VOLUME = 0.8

# Two tracks added together can pass full scale, so cap the sum.
LIMIT = 0.95


class FFmpegError(Exception):
    """Error for a failed ffmpeg or ffprobe call."""


@dataclass
class MediaInfo:
    """What ffprobe says about one file."""

    duration_ms: int = 0
    video_ms: int = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_video: bool = False
    has_audio: bool = False


def missing_tools() -> list[str]:
    """Return the names of the tools that are not on the path."""
    return [name for name in (FFMPEG, FFPROBE) if shutil.which(name) is None]


def run(args: list[str]) -> str:
    """Run one ffmpeg or ffprobe command and return what it printed."""
    try:
        done = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise FFmpegError(f"cannot run {args[0]}: {exc}") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip()
        raise FFmpegError(detail[-ERROR_TAIL:] or f"{args[0]} failed")
    return done.stdout


def probe(path: str | Path) -> MediaInfo:
    """Return the duration, size and streams of one file."""
    reply = run(
        [
            FFPROBE,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    try:
        data = json.loads(reply or "{}")
    except json.JSONDecodeError as exc:
        raise FFmpegError("ffprobe reply is not JSON") from exc

    info = MediaInfo(duration_ms=_ms(data.get("format", {}).get("duration")))
    for stream in data.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "video" and not info.has_video:
            info.has_video = True
            info.video_ms = _video_ms(stream)
            info.width = int(stream.get("width") or 0)
            info.height = int(stream.get("height") or 0)
            info.fps = _fps(stream.get("r_frame_rate"))
        elif kind == "audio":
            info.has_audio = True
    return info


def mux(
    clip: str | Path,
    audio: str | Path,
    target: str | Path,
    *,
    seconds: float = 0.0,
    hold: float = 0.0,
) -> Path:
    """Put one audio track under one clip, cutting both to seconds.

    The sound the model put in the clip is replaced, not mixed. A hold
    keeps the last picture on screen for that long, with silence under it.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    args = [
        FFMPEG,
        *COMMON,
        "-i",
        str(clip),
        "-i",
        str(audio),
    ]
    if hold > 0:
        args += [
            "-filter_complex",
            f"[0:v]tpad=stop_mode=clone:stop_duration={hold:.3f}[v]",
            "-map",
            "[v]",
        ]
    else:
        args += ["-map", "0:v:0"]
    args += [
        "-map",
        "1:a:0",
        "-af",
        "apad",
    ]
    if seconds > 0:
        args += ["-t", f"{seconds:.3f}"]
    args += [*VIDEO_CODEC, *AUDIO_CODEC, *FASTSTART, str(target)]
    run(args)
    return target


def mix(
    clip: str | Path,
    audio: str | Path,
    target: str | Path,
    *,
    seconds: float = 0.0,
    background: float = BACKGROUND_VOLUME,
    hold: float = 0.0,
) -> Path:
    """Put one track over the sound a clip already carries, cut to seconds.

    The clip has to bring its own sound; a silent clip goes through mux().
    A hold keeps the last picture on screen for that long, with only the
    local track under it.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # The model's own sound can be shorter than the local track, so the
    # mix runs to the longer of the two and the tail is padded with silence.
    graph = (
        f"[0:a]volume={background:g}[bg];"
        "[bg][1:a]amix=inputs=2:duration=longest:normalize=0,"
        f"apad,alimiter=limit={LIMIT:g}[a]"
    )
    picture = "0:v:0"
    if hold > 0:
        graph += f";[0:v]tpad=stop_mode=clone:stop_duration={hold:.3f}[v]"
        picture = "[v]"
    args = [
        FFMPEG,
        *COMMON,
        "-i",
        str(clip),
        "-i",
        str(audio),
        "-filter_complex",
        graph,
        "-map",
        picture,
        "-map",
        "[a]",
    ]
    if seconds > 0:
        args += ["-t", f"{seconds:.3f}"]
    args += [*VIDEO_CODEC, *AUDIO_CODEC, *FASTSTART, str(target)]
    run(args)
    return target


def concat(sources: list[str | Path], target: str | Path) -> Path:
    """Join clips that share size, frame rate, codecs and audio layout."""
    if not sources:
        raise FFmpegError("nothing to join")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as listing:
        for source in sources:
            listing.write(f"file '{Path(source).resolve()}'\n")
        name = listing.name
    try:
        run(
            [
                FFMPEG,
                *COMMON,
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                name,
                "-c",
                "copy",
                *FASTSTART,
                str(target),
            ]
        )
    finally:
        Path(name).unlink(missing_ok=True)
    return target


def join(
    sources: list[str | Path],
    target: str | Path,
    *,
    overlaps: list[float] | None = None,
) -> Path:
    """Join clips, dissolving where the overlaps say so.

    overlaps[i] is the length shared by clip i and clip i+1; zero means a
    hard cut, and a list of zeros takes the copy-only path of concat().
    Clips that hard cut into each other are joined with concat first, because
    a cross fade of zero length is not a hard cut.
    Nothing is thrown away: every take keeps its whole picture and its whole
    sound. Each take ends with a held beat, so the stretch a dissolve shares
    holds no words and the sound can be cut there without losing any.
    """
    sources = [Path(source) for source in sources]
    if not sources:
        raise FFmpegError("nothing to join")
    spreads = list(overlaps or [0.0] * (len(sources) - 1))
    if len(spreads) != len(sources) - 1:
        raise FFmpegError("one overlap per join is required")
    if not any(spreads):
        return concat(sources, target)

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    lengths = [probe(source).duration_ms / 1000 for source in sources]
    size = probe(sources[0])
    runs = _runs(spreads)
    edges = []
    for number, length in enumerate(lengths):
        tail = spreads[number] if number < len(spreads) else 0.0
        if number not in [group[-1] for group in runs]:
            tail = 0.0
        keep = max(0.0, length - tail)
        # Both streams are held at the length they keep, so a track that
        # came out a frame short cannot pull the film out of step.
        edges.append(f"[{number}:v]{_fit(size)}[v{number}]")
        edges.append(
            f"[{number}:a]atrim=0:{keep:.3f},"
            f"apad=whole_dur={keep:.3f},asetpts=PTS-STARTPTS[a{number}]"
        )

    for number, group in enumerate(runs):
        edges.append(_pieced("v", group, f"gv{number}"))
        edges.append(_pieced("a", group, f"ga{number}"))

    label = "gv0"
    end = _run_length(runs[0], lengths)
    for number in range(1, len(runs)):
        spread = spreads[runs[number - 1][-1]]
        offset = end - spread
        edges.append(
            f"[{label}][gv{number}]xfade=transition=fade"
            f":duration={spread:.3f}:offset={offset:.3f}[x{number}]"
        )
        label = f"x{number}"
        end = offset + _run_length(runs[number], lengths)

    edges.append(
        "".join(f"[ga{number}]" for number in range(len(runs)))
        + f"concat=n={len(runs)}:v=0:a=1[a]"
    )
    args = [FFMPEG, *COMMON]
    for source in sources:
        args += ["-i", str(source)]
    args += [
        "-filter_complex",
        ";".join(edges),
        "-map",
        f"[{label}]",
        "-map",
        "[a]",
        *VIDEO_CODEC,
        *AUDIO_CODEC,
        *FASTSTART,
        str(target),
    ]
    run(args)
    return target


# Hold one card image for a while, its sound under it.
def title_card(
    still: str | Path,
    audio: str | Path,
    target: str | Path,
    *,
    size: tuple[int, int],
    seconds: float,
    fade: float = 0.4,
) -> Path:
    """Hold a card image for the given time, sounding its audio."""
    width, height = size
    seconds = int(seconds * FILM_FPS) / FILM_FPS
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    graph = (
        f"fade=t=in:st=0:d={fade:g},"
        f"fade=t=out:st={seconds - fade:.3f}:d={fade:g},"
        f"fps={FILM_FPS},scale={width}:{height},setsar=1,"
        "format=yuv420p"
    )
    run(
        [
            FFMPEG,
            *COMMON,
            "-loop",
            "1",
            "-i",
            str(still),
            "-i",
            str(audio),
            "-filter_complex",
            f"[0:v]{graph}[v]",
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            "-af",
            "apad",
            "-t",
            f"{seconds:.3f}",
            *VIDEO_CODEC,
            *AUDIO_CODEC,
            *FASTSTART,
            str(target),
        ]
    )
    return target


# Split the takes into runs that hard cut into each other.
def _runs(spreads: list[float]) -> list[list[int]]:
    runs = [[0]]
    for number in range(1, len(spreads) + 1):
        if spreads[number - 1] > 0:
            runs.append([number])
        else:
            runs[-1].append(number)
    return runs


# Return how long one run lasts once its takes are joined.
def _run_length(group: list[int], lengths: list[float]) -> float:
    return sum(lengths[number] for number in group)


# Join the takes of one run into a single stream, or pass it through alone.
def _pieced(kind: str, group: list[int], label: str) -> str:
    if len(group) == 1:
        filler = "null" if kind == "v" else "anull"
        chain = f"[{kind}{group[0]}]{filler}"
    else:
        parts = "".join(f"[{kind}{number}]" for number in group)
        flags = "v=1:a=0" if kind == "v" else "v=0:a=1"
        chain = f"{parts}concat=n={len(group)}:{flags}"
    if kind == "v":
        # Cross fades only accept inputs that share a time base.
        chain += ",settb=1/24"
    return f"{chain}[{label}]"


def frame(
    path: str | Path,
    target: str | Path,
    *,
    last: bool = False,
) -> Path:
    """Write the first or the last picture of a clip to target."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    args = [FFMPEG, *COMMON]
    if last:
        length = probe(path).duration_ms / 1000
        args += ["-sseof", f"-{min(length, 0.2):.3f}"]
    args += ["-i", str(path), "-frames:v", "1", "-update", "1", str(target)]
    run(args)
    return target


# Fit one input to the size and frame rate the film uses.
def _fit(size: MediaInfo) -> str:
    return (
        f"fps={FILM_FPS},scale={size.width}:{size.height},setsar=1,"
        "format=yuv420p,setpts=PTS-STARTPTS"
    )


# Read a duration in seconds into whole milliseconds.
def _ms(value: object) -> int:
    try:
        return round(float(value) * 1000)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read a video stream's own length, or work it out from its frame count.
def _video_ms(stream: dict) -> int:
    direct = _ms(stream.get("duration"))
    if direct:
        return direct
    frames = int(stream.get("nb_frames") or 0)
    fps = _fps(stream.get("r_frame_rate"))
    if frames and fps:
        return round(frames * 1000 / fps)
    return 0


# Read a frame rate written as a fraction, like 24000/1001.
def _fps(value: object) -> float:
    text = str(value or "")
    top, _, bottom = text.partition("/")
    try:
        return float(top) / float(bottom or 1)
    except ValueError:
        return 0.0
