import json
import struct
import wave

import pytest
from aura_paper.media import ffmpeg
from aura_paper.schema.job import BookJobs
from aura_paper.stages.compose import compose
from aura_paper.store.output import write_json

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
def make_book(
    root,
    *,
    tone=False,
    with_line=True,
    audio_ms=1000,
    shots=1,
    join="硬切",
    clip_seconds=2.0,
):
    book = root / "demo"
    entries = []
    for number in range(shots):
        name = f"j{number + 1}"
        make_clip(
            book / "clips" / f"{name}.mp4", seconds=clip_seconds, tone=tone
        )
        lines = []
        if with_line:
            make_line(book / "voice" / f"{name}-0.wav")
            lines.append(
                {
                    "index": 0,
                    "kind": "旁白",
                    "text": "下",
                    "file": f"voice/{name}-0.wav",
                    "start_ms": 0,
                    "duration_ms": 500,
                }
            )
        entries.append(
            {
                "shot": name,
                "prompt": "p",
                "duration": 2,
                "audio_ms": audio_ms,
                "join": join if number else "叠化",
                "lines": lines,
            }
        )
    jobs = BookJobs.from_dict(
        {
            "id": "demo",
            "ratio": "4:3",
            "resolution": "480p",
            "shots": entries,
        }
    )
    write_json("demo", "jobs", jobs.to_dict(), root)


def test_keeps_the_whole_clip_even_when_the_lines_are_short(tmp_path):
    make_book(tmp_path, audio_ms=1200)

    result = compose("demo", root=tmp_path)

    take = result.shots[0]
    assert take.error == ""
    assert take.file == "shots/j1.mp4"
    assert take.audio == "shots/j1.wav"
    assert take.seconds == pytest.approx(2.5)
    info = ffmpeg.probe(tmp_path / "demo" / "shots" / "j1.mp4")
    assert info.has_audio is True
    assert info.duration_ms == pytest.approx(2500, abs=120)


def test_leaves_the_dialogue_to_the_clip_that_was_sent_a_reference(tmp_path):
    make_book(tmp_path, tone=True)
    path = tmp_path / "demo" / "jobs.json"
    data = json.loads(path.read_text("utf-8"))
    data["shots"][0]["reference"] = "jobs/j1-ref.wav"
    data["shots"][0]["lines"][0]["kind"] = "对白"
    path.write_text(json.dumps(data), "utf-8")

    result = compose("demo", root=tmp_path)

    # The model spoke that line itself, so the local track stays silent.
    track = (tmp_path / "demo" / "shots" / "j1.wav").read_bytes()[44:]
    assert set(track) == {0}
    info = ffmpeg.probe(tmp_path / "demo" / "shots" / "j1.mp4")
    assert info.has_audio is True
    assert "旁白时段画面有声音" not in result.shots[0].error


def test_reports_a_line_that_runs_into_the_end_of_the_clip(tmp_path):
    make_book(tmp_path, tone=True)
    path = tmp_path / "demo" / "jobs.json"
    data = json.loads(path.read_text("utf-8"))
    data["shots"][0]["reference"] = "jobs/j1-ref.wav"
    data["shots"][0]["lines"][0]["kind"] = "对白"
    path.write_text(json.dumps(data), "utf-8")

    result = compose("demo", root=tmp_path)

    # The tone runs to the last frame, so the words had no room left.
    assert "台词贴到片尾" in result.shots[0].error


def test_a_take_is_as_long_as_its_clip_and_its_hold(tmp_path):
    make_book(tmp_path, audio_ms=600, clip_seconds=1.0)

    result = compose("demo", root=tmp_path)

    assert result.shots[0].seconds == pytest.approx(1.5, abs=0.1)


def test_keeps_the_sound_the_clip_brought(tmp_path):
    make_book(tmp_path, tone=True, audio_ms=1000)

    result = compose("demo", root=tmp_path)

    assert result.shots[0].sound is True
    assert _peak(tmp_path / "demo" / "shots" / "j1.mp4", tmp_path) > 0


def test_keeps_the_whole_clip_when_nothing_is_spoken(tmp_path):
    make_book(tmp_path, with_line=False, audio_ms=600)

    result = compose("demo", root=tmp_path)

    # A sound effect alone must not cut the picture down to its slot.
    assert result.shots[0].seconds == pytest.approx(2.5, abs=0.1)


def test_joins_the_takes_into_a_film(tmp_path):
    make_book(tmp_path, shots=2, join="硬切", audio_ms=1000)

    result = compose("demo", root=tmp_path)

    assert result.film == "shots/film.mp4"
    assert (tmp_path / "demo" / "shots" / "film.mp4").is_file()
    # Two whole clips and their holds, cut together without losing anything.
    assert result.seconds == pytest.approx(5.0, abs=0.1)
    assert [shot.start for shot in result.shots] == [0.0, 2.5]
    assert [join.after for join in result.joins] == ["j2"]
    assert result.joins[0].kind == "硬切"


def test_a_dissolve_costs_the_length_it_shares(tmp_path):
    make_book(tmp_path, shots=2, join="叠化", audio_ms=1000)

    result = compose("demo", root=tmp_path)

    assert result.seconds == pytest.approx(4.5, abs=0.1)
    # The two sounds run into each other, so the film is as long as its
    # picture and the sound is not cut short.
    info = ffmpeg.probe(tmp_path / "demo" / "shots" / "film.mp4")
    assert info.duration_ms == pytest.approx(4500, abs=120)


def test_waits_for_every_shot_before_making_the_film(tmp_path):
    make_book(tmp_path, shots=2, audio_ms=1000)
    (tmp_path / "demo" / "clips" / "j2.mp4").unlink()

    result = compose("demo", root=tmp_path)

    assert result.film == ""
    assert "没出片" in result.error


def test_records_a_shot_that_has_no_clip_yet(tmp_path):
    make_book(tmp_path)
    (tmp_path / "demo" / "clips" / "j1.mp4").unlink()

    result = compose("demo", root=tmp_path)

    assert result.shots[0].error == "还没有生成这一镜"
    # A clip that is still being made is not a failure of this stage.
    assert result.error == "还有 1 镜没出片，先不拼整片"


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


def test_reports_sound_where_the_narration_should_be_quiet(tmp_path):
    make_book(tmp_path, tone=True)
    path = tmp_path / "demo" / "jobs.json"
    data = json.loads(path.read_text("utf-8"))
    data["shots"][0]["reference"] = "jobs/j1-ref.wav"
    data["shots"][0]["lines"][0]["duration_ms"] = 1500
    path.write_text(json.dumps(data), "utf-8")

    result = compose("demo", root=tmp_path)

    # The clip talked over the stretch that held no words.
    assert "旁白时段画面有声音" in result.shots[0].error
