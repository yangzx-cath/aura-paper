import struct
import wave

import pytest

from aura_paper.media import ffmpeg
from aura_paper.output import write_json
from aura_paper.schema.job import BookJobs
from aura_paper.stages.compose import compose

# These tests run the real tools, so skip them where they are missing.
pytestmark = pytest.mark.skipif(
    bool(ffmpeg.missing_tools()),
    reason="ffmpeg is not installed",
)

RATE = 24000


# Write a clip, with a tone when the shot is meant to bring its own sound.
def make_clip(path, seconds=2.0, tone=False):
    args = [
        ffmpeg.FFMPEG,
        *ffmpeg.COMMON,
        "-f",
        "lavfi",
        "-i",
        f"color=c=gray:s=752x560:d={seconds}:r=24",
    ]
    if tone:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if tone:
        args += ["-c:a", "aac", "-shortest"]
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run([*args, str(path)])


# Write a spoken line the way the speech client does.
def make_line(path, seconds=0.5):
    pcm = b"\x01\x02" * int(RATE * seconds)
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + pcm)


# Write what the jobs and render stages would have left behind.
def make_book(root, *, tone=False, with_line=True, audio_ms=1000):
    book = root / "demo"
    make_clip(book / "clips" / "j1.mp4", seconds=2.0, tone=tone)
    if with_line:
        make_line(book / "voice" / "j1-0.wav")

    lines = []
    if with_line:
        lines.append(
            {
                "index": 0,
                "kind": "旁白",
                "text": "下",
                "file": "voice/j1-0.wav",
                "start_ms": 0,
                "duration_ms": 500,
            }
        )
    jobs = BookJobs.from_dict(
        {
            "id": "demo",
            "ratio": "4:3",
            "resolution": "480p",
            "shots": [
                {
                    "shot": "j1",
                    "prompt": "p",
                    "duration": 2,
                    "audio_ms": audio_ms,
                    "lines": lines,
                }
            ],
        }
    )
    write_json("demo", "jobs", jobs.to_dict(), root)


def test_mixes_a_take_as_long_as_the_lines_run(tmp_path):
    make_book(tmp_path, audio_ms=1200)

    result = compose("demo", root=tmp_path)

    take = result.shots[0]
    assert take.error == ""
    assert take.file == "shots/j1.mp4"
    assert take.audio == "shots/j1.wav"
    assert take.seconds == pytest.approx(1.2)
    info = ffmpeg.probe(tmp_path / "demo" / "shots" / "j1.mp4")
    assert info.has_audio is True
    assert info.duration_ms == pytest.approx(1200, abs=120)


def test_keeps_the_sound_the_clip_brought(tmp_path):
    make_book(tmp_path, tone=True, audio_ms=1000)

    result = compose("demo", root=tmp_path)

    assert result.shots[0].sound is True
    assert _peak(tmp_path / "demo" / "shots" / "j1.mp4", tmp_path) > 0


def test_keeps_the_whole_clip_when_nothing_is_spoken(tmp_path):
    make_book(tmp_path, with_line=False, audio_ms=600)

    result = compose("demo", root=tmp_path)

    # A sound effect alone must not cut the picture down to its slot.
    assert result.shots[0].seconds == pytest.approx(2.0, abs=0.1)


def test_records_a_shot_that_has_no_clip_yet(tmp_path):
    make_book(tmp_path)
    (tmp_path / "demo" / "clips" / "j1.mp4").unlink()

    result = compose("demo", root=tmp_path)

    assert result.shots[0].error == "还没有生成这一镜"
    assert "还没有生成这一镜" in result.error


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
            str(raw),
        ]
    )
    with wave.open(str(raw)) as handle:
        frames = handle.readframes(handle.getnframes())
    return max(abs(value) for value in _samples(frames))


# Read 16-bit samples out of a byte string.
def _samples(frames):
    import array

    return array.array("h", frames)
