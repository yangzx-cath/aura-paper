import pytest
from aura_paper.clients.reply import extract_json


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
