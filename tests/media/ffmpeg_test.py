import struct

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
def make_clip(path, seconds=1.0, size=SIZE):
    ffmpeg.run(
        [
            ffmpeg.FFMPEG,
            *ffmpeg.COMMON,
            "-f",
            "lavfi",
            "-i",
            f"color=c=gray:s={size}:d={seconds}:r=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


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


def test_joins_clips_that_share_their_parameters(tmp_path):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    make_clip(first, seconds=1.0)
    make_clip(second, seconds=0.5)

    target = ffmpeg.concat([first, second], tmp_path / "film.mp4")

    assert ffmpeg.probe(target).duration_ms == pytest.approx(1500, abs=120)


def test_reports_a_bad_call(tmp_path):
    with pytest.raises(FFmpegError):
        ffmpeg.probe(tmp_path / "missing.mp4")
