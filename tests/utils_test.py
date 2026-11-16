import base64
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aura_paper.utils import data_url, extract_json, now_iso

SAMPLE_JPG = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "chicken_and_sunflower"
    / "01.jpg"
)


def test_jpeg_prefix_and_payload():
    url = data_url(SAMPLE_JPG)

    header, _, payload = url.partition(",")
    assert header == "data:image/jpeg;base64"
    assert base64.b64decode(payload) == SAMPLE_JPG.read_bytes()


def test_png_uses_png_mime(tmp_path):
    target = tmp_path / "page.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")

    url = data_url(target)

    assert url.startswith("data:image/png;base64,")


def test_upper_suffix_uses_mime(tmp_path):
    target = tmp_path / "page.JPG"
    target.write_bytes(b"\xff\xd8fake")

    url = data_url(target)

    assert url.startswith("data:image/jpeg;base64,")


@pytest.mark.parametrize("suffix", [".bmp", ".webp", ".heic"])
def test_removed_format_raises(tmp_path, suffix):
    target = tmp_path / f"page{suffix}"
    target.write_bytes(b"x")

    with pytest.raises(ValueError, match="unsupported image type"):
        data_url(target)


def test_unknown_suffix_raises(tmp_path):
    target = tmp_path / "page.xyz"
    target.write_bytes(b"whatever")

    with pytest.raises(ValueError, match="unsupported image type"):
        data_url(target)


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_after_prose():
    assert extract_json('结果如下：\n{"a": 1}\n以上') == {"a": 1}


def test_extract_takes_first_object():
    assert extract_json('{"a": 1}\n{"b": 2}') == {"a": 1}


def test_extract_without_json_raises():
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json("抱歉，我无法完成")


def test_extract_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")


def test_extract_invalid_json_raises():
    with pytest.raises(ValueError, match="invalid JSON"):
        extract_json("{oops")


def test_now_iso_is_utc():
    value = now_iso()
    parsed = datetime.fromisoformat(value)

    assert parsed.tzinfo == timezone.utc
    assert parsed.microsecond == 0
