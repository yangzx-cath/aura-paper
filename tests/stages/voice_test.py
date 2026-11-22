import json

from aura_paper.cache import Cache
from aura_paper.clients.tts import TTSClient, TTSError
from aura_paper.output import write_json
from aura_paper.schema.cast import BookCast
from aura_paper.schema.shot import BookShots
from aura_paper.schema.voice import NARRATOR
from aura_paper.stages.voice import voice

# 24000 bytes of 16-bit mono at 24000 Hz is half a second.
HALF_SECOND = b"\x01\x02" * 12000

WAV_HEADER = 44

# The voice the cast stage gives the girl in these books.
GIRL = "zh_female_xiaoxue_uranus_bigtts"


# Return a WAV file holding one second of silence per character.
def wav(characters: int) -> bytes:
    pcm = b"\x00\x00" * (24000 * characters)
    header = b"RIFF" + b"\x00" * 40
    return header + pcm


# Speak with a length that depends only on the text, and count the calls.
class FakeTTS(TTSClient):
    def __init__(self, failing=()):
        super().__init__(
            base_url="https://example/v3",
            api_key="key-1",
            resource_id="seed-tts-2.0",
        )
        self.texts = []
        self.failing = set(failing)

    def synthesize(self, text, *, voice, speed=1.0, emotion=""):
        self.texts.append((text, voice))
        if text in self.failing:
            raise TTSError("speaker permission denied")
        return _speech(text, voice)


# Build the object the client would return.
def _speech(text, voice):
    from aura_paper.clients.tts import Speech

    data = wav(len(text))
    return Speech(
        text=text, voice=voice, data=data, duration_ms=len(text) * 1000
    )


# Write the shots artifact the stage reads.
def make_shots(root, shots):
    make_book = root / "demo"
    make_book.mkdir(parents=True, exist_ok=True)
    book = BookShots.from_dict({"id": "demo", "shots": shots})
    write_json("demo", "shots", book.to_dict(), root)


# Write the cast artifact the stage reads.
def make_cast(root, voices):
    make_book = root / "demo"
    make_book.mkdir(parents=True, exist_ok=True)
    members = [{"id": key, "voice": value} for key, value in voices.items()]
    book = BookCast.from_dict({"id": "demo", "cast": members})
    write_json("demo", "cast", book.to_dict(), root)


# One sound line of a shot.
def line(kind, text, cast="", spoken=""):
    entry = {"kind": kind, "text": text, "cast": cast}
    if spoken:
        entry["spoken"] = spoken
    return entry


# One shot with the panels and sounds given.
def shot(shot_id, audio):
    return {
        "id": shot_id,
        "panels": [{"page": "p000.jpg", "panel": 0}],
        "audio": audio,
    }


def test_speaks_every_line_and_measures_the_shot(tmp_path):
    make_shots(
        tmp_path,
        [
            shot(
                "j1",
                [
                    line("旁白", "下", spoken="滴答"),
                    line("对白", "好", cast="c1"),
                    line("音效", "阿嚏！"),
                ],
            )
        ],
    )
    make_cast(tmp_path, {"c1": GIRL})
    tts = FakeTTS()

    result = voice("demo", tts=tts, gap_ms=300, root=tmp_path)

    # The sound effect is never spoken.
    assert tts.texts == [("滴答", NARRATOR), ("好", GIRL)]
    spoken = result.shots[0].lines
    assert [item.voice for item in spoken] == [NARRATOR, GIRL]
    # Two seconds for 滴答, one for 好, and one gap between them.
    assert result.shots[0].duration_ms == 3000 + 300
    assert result.error == ""
    assert (tmp_path / "demo" / "voice" / "j1-0.wav").is_file()
    assert (tmp_path / "demo" / "voice" / "j1-1.wav").is_file()


def test_takes_a_voice_from_the_command_line_over_the_cast(tmp_path):
    make_shots(tmp_path, [shot("j1", [line("对白", "好", cast="c1")])])
    make_cast(tmp_path, {"c1": GIRL})
    tts = FakeTTS()

    result = voice("demo", tts=tts, overrides={"c1": "other"}, root=tmp_path)

    assert tts.texts == [("好", "other")]
    assert result.shots[0].lines[0].voice == "other"


def test_uses_the_spoken_text_when_there_is_one(tmp_path):
    make_shots(tmp_path, [shot("j1", [line("旁白", "原文", spoken="改过")])])
    make_cast(tmp_path, {})
    tts = FakeTTS()

    result = voice("demo", tts=tts, root=tmp_path)

    assert tts.texts == [("改过", NARRATOR)]
    spoken = result.shots[0].lines[0]
    assert spoken.text == "原文"
    assert spoken.spoken == "改过"


def test_stops_before_spending_anything_when_a_voice_is_missing(tmp_path):
    make_shots(
        tmp_path,
        [
            shot(
                "j1",
                [line("旁白", "下"), line("对白", "好", cast="c1")],
            )
        ],
    )
    tts = FakeTTS()
    make_cast(tmp_path, {})

    result = voice("demo", tts=tts, root=tmp_path)

    assert tts.texts == []
    assert "c1" in result.error
    assert result.shots == []
    assert (tmp_path / "demo" / "voice.json").is_file()


def test_gives_a_shot_without_lines_no_length(tmp_path):
    make_shots(tmp_path, [shot("j1", [])])
    make_cast(tmp_path, {})

    result = voice("demo", tts=FakeTTS(), root=tmp_path)

    assert result.shots[0].duration_ms == 0
    assert result.shots[0].lines == []


def test_reuses_the_cached_audio(tmp_path):
    make_shots(tmp_path, [shot("j1", [line("旁白", "下")])])
    make_cast(tmp_path, {})
    tts = FakeTTS()
    cache = Cache(tmp_path / "cache")

    first = voice("demo", tts=tts, root=tmp_path, cache=cache)
    second = voice(
        "demo",
        tts=tts,
        root=tmp_path,
        cache=Cache(tmp_path / "cache"),
    )

    assert len(tts.texts) == 1
    assert second.shots[0].duration_ms == first.shots[0].duration_ms
    assert (tmp_path / "cache" / "voice").is_dir()


def test_records_a_failed_line_and_keeps_the_file(tmp_path):
    make_shots(
        tmp_path,
        [
            shot("j1", [line("旁白", "好")]),
            shot("j2", [line("旁白", "坏")]),
        ],
    )
    tts = FakeTTS(failing={"坏"})
    make_cast(tmp_path, {})

    result = voice("demo", tts=tts, root=tmp_path)

    assert "j2" in result.error
    assert [item.shot for item in result.shots] == ["j1"]
    assert (tmp_path / "demo" / "voice.json").is_file()


def test_reads_its_own_artifact_back(tmp_path):
    make_shots(tmp_path, [shot("j1", [line("旁白", "下")])])
    make_cast(tmp_path, {"c1": GIRL})
    voice("demo", tts=FakeTTS(), root=tmp_path)

    saved = json.loads((tmp_path / "demo" / "voice.json").read_text())

    assert saved["resource_id"] == "seed-tts-2.0"
    assert saved["voices"] == {"旁白": NARRATOR, "c1": GIRL}
    assert saved["shots"][0]["lines"][0]["file"] == "voice/j1-0.wav"
