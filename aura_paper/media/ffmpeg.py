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
) -> Path:
    """Put one audio track under one clip, cutting both to seconds.

    The sound the model put in the clip is replaced, not mixed.
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
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
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
) -> Path:
    """Put one track over the sound a clip already carries, cut to seconds.

    The clip has to bring its own sound; a silent clip goes through mux().
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    graph = (
        f"[0:a]volume={background:g}[bg];"
        "[bg][1:a]amix=inputs=2:duration=first:normalize=0,"
        f"alimiter=limit={LIMIT:g}[a]"
    )
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
        "0:v:0",
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
    The sound of a dissolve is cut at the overlap, not cross faded, so the
    words of the next shot stay whole.
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
    edges = []
    audio = []
    for number, source in enumerate(sources):
        spread = spreads[number] if number < len(spreads) else 0.0
        keep = max(0.0, lengths[number] - spread)
        edges.append(f"[{number}:v]{_fit(size)}[v{number}]")
        edges.append(f"[{number}:a]atrim=0:{keep:.3f}[a{number}]")
        audio.append(f"[a{number}]")

    label = "v0"
    end = lengths[0]
    for number in range(1, len(sources)):
        spread = spreads[number - 1]
        offset = end - spread
        nxt = f"x{number}"
        edges.append(
            f"[{label}][v{number}]xfade=transition=fade"
            f":duration={spread:.3f}:offset={offset:.3f}[{nxt}]"
        )
        label = nxt
        end = offset + lengths[number]

    edges.append("".join(audio) + f"concat=n={len(sources)}:v=0:a=1[a]")
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
        f"fps=24,scale={size.width}:{size.height},setsar=1,"
        "format=yuv420p,setpts=PTS-STARTPTS"
    )


# Read a duration in seconds into whole milliseconds.
def _ms(value: object) -> int:
    try:
        return round(float(value) * 1000)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# Read a frame rate written as a fraction, like 24000/1001.
def _fps(value: object) -> float:
    text = str(value or "")
    top, _, bottom = text.partition("/")
    try:
        return float(top) / float(bottom or 1)
    except ValueError:
        return 0.0
