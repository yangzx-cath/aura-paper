from aura_paper.schema.voice import (
    CHINESE_CHOICES,
    CHOICES_BY_LANGUAGE,
    ENGLISH_CHOICES,
    narrator_for,
)


def test_each_language_has_its_own_table():
    assert all(voice.startswith("zh_") for voice, _ in CHINESE_CHOICES)
    assert all(voice.startswith("en_") for voice, _ in ENGLISH_CHOICES)
    assert CHOICES_BY_LANGUAGE["zh"] is CHINESE_CHOICES
    assert CHOICES_BY_LANGUAGE["en"] is ENGLISH_CHOICES


def test_the_narrator_follows_the_language():
    assert narrator_for("en") in [voice for voice, _ in ENGLISH_CHOICES]
    assert narrator_for("zh") in [voice for voice, _ in CHINESE_CHOICES]
    assert narrator_for("") in [voice for voice, _ in CHINESE_CHOICES]
