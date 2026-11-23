import array
import struct
import wave

import pytest

from aura_paper.media import ffmpeg
from aura_paper.media.ffmpeg import FFmpegError

# These tests run the real tools, so skip them where they are missing.
pytestmark = pytest.mark.skipif(
    bool(ffmpeg.missing_tools()),
    reason="ffmpeg is not installed",
)

# A silent clip with the size and frame rate the stages use.
SIZE = "752x560"

# The sample rate the speech client returns.
RATE = 24000


# Write a plain clip, the way the video model would hand one back.
def make_clip(path, seconds=1.0, size=SIZE, tone=False):
    args = [
        ffmpeg.FFMPEG,
        *ffmpeg.COMMON,
        "-f",
        "lavfi",
        "-i",
        f"color=c=gray:s={size}:d={seconds}:r=24",
    ]
    if tone:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if tone:
        args += ["-c:a", "aac", "-shortest"]
    ffmpeg.run([*args, str(path)])


# Write a WAV of silence, like the ones the voice stage builds.
def make_wav(path, seconds=0.5):
    pcm = b"\x00\x00" * int(RATE * seconds)
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    path.write_bytes(header + pcm)


def test_probes_the_size_and_length_of_a_clip(tmp_path):
    clip = tmp_path / "clip.mp4"
    make_clip(clip, seconds=1.5)

    info = ffmpeg.probe(clip)

    assert info.has_video is True
    assert info.has_audio is False
    assert (info.width, info.height) == (752, 560)
    assert info.fps == pytest.approx(24.0)
    assert info.duration_ms == pytest.approx(1500, abs=80)


def test_puts_a_track_under_a_clip_and_cuts_it(tmp_path):
    clip = tmp_path / "clip.mp4"
    wav = tmp_path / "line.wav"
    make_clip(clip, seconds=2.0)
    make_wav(wav)

    target = ffmpeg.mux(clip, wav, tmp_path / "shot.mp4", seconds=1.0)

    info = ffmpeg.probe(target)
    assert info.has_audio is True
    assert info.duration_ms == pytest.approx(1000, abs=80)


def test_keeps_the_sound_of_a_clip_under_the_track(tmp_path):
    clip = tmp_path / "clip.mp4"
    wav = tmp_path / "line.wav"
    make_clip(clip, seconds=1.0, tone=True)
    make_wav(wav)

    target = ffmpeg.mix(clip, wav, tmp_path / "shot.mp4", seconds=1.0)

    info = ffmpeg.probe(target)
    assert info.has_audio is True
    assert info.duration_ms == pytest.approx(1000, abs=80)
    # The track is silent, so any sound left is the one the clip came with.
    assert _peak(target, tmp_path) > 0


def test_joins_clips_that_share_their_parameters(tmp_path):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    make_clip(first, seconds=1.0)
    make_clip(second, seconds=0.5)

    target = ffmpeg.concat([first, second], tmp_path / "film.mp4")

    assert ffmpeg.probe(target).duration_ms == pytest.approx(1500, abs=120)


def test_joins_a_mix_of_cuts_and_dissolves(tmp_path):
    clips = []
    for number, seconds in enumerate((1.0, 1.5, 2.0), start=1):
        path = tmp_path / f"s{number}.mp4"
        make_clip(path, seconds=seconds, tone=True)
        clips.append(path)

    target = ffmpeg.join(clips, tmp_path / "film.mp4", overlaps=[0.5, 0.0])

    # A zero length cross fade is not a hard cut, so the middle join must
    # stay a cut and the whole film must keep the length it should have.
    assert ffmpeg.probe(target).duration_ms == pytest.approx(4000, abs=150)


def test_reports_a_bad_call(tmp_path):
    with pytest.raises(FFmpegError):
        ffmpeg.probe(tmp_path / "missing.mp4")


# Return the loudest sample of a file's audio, read back as plain PCM.
def _peak(path, folder):
    raw = folder / "raw.wav"
    ffmpeg.run(
        [
            ffmpeg.FFMPEG,
            *ffmpeg.COMMON,
            "-i",
            str(path),
            "-vn",
            "-c:a",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(RATE),
            str(raw),
        ]
    )
    with wave.open(str(raw)) as handle:
        frames = handle.readframes(handle.getnframes())
    samples = array.array("h", frames)
    return max(abs(value) for value in samples)
