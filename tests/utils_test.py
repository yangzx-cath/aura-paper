import base64
from datetime import datetime, timezone

import pytest

from aura_paper.utils import data_url, extract_json, now_iso


def test_jpeg_prefix_and_payload(sample_jpeg):
    url = data_url(sample_jpeg)

    header, _, payload = url.partition(",")
    assert header == "data:image/jpeg;base64"
    assert base64.b64decode(payload) == sample_jpeg.read_bytes()


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


def test_unknown_suffix_raises(tmp_path):
    target = tmp_path / "page.xyz"
    target.write_bytes(b"whatever")

    with pytest.raises(ValueError, match="unsupported image type"):
        data_url(target)


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_without_json_raises():
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json("抱歉，我无法完成")


def test_extract_invalid_json_raises():
    with pytest.raises(ValueError, match="invalid JSON"):
        extract_json("{oops")


def test_now_iso_is_utc():
    value = now_iso()
    parsed = datetime.fromisoformat(value)

    assert parsed.tzinfo == timezone.utc
    assert parsed.microsecond == 0
