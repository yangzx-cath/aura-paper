import hashlib
import re
from pathlib import Path

import pytest

from aura_paper.cache import file_fingerprint, fingerprint


def test_returns_16_hex_characters():
    key = fingerprint("understand-page-v1", "abc")
    assert re.fullmatch(r"[0-9a-f]{16}", key)


def test_is_stable_across_calls():
    first = fingerprint("understand-page-v1", "abc", "qwen3.8-max")
    second = fingerprint("understand-page-v1", "abc", "qwen3.8-max")
    assert first == second


def test_dict_key_order_does_not_matter():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_nested_dict_key_order_does_not_matter():
    left = fingerprint({"pages": [{"a": 1, "b": 2}]})
    right = fingerprint({"pages": [{"b": 2, "a": 1}]})
    assert left == right


def test_list_order_matters():
    assert fingerprint(["a", "b"]) != fingerprint(["b", "a"])


def test_argument_boundaries_matter():
    assert fingerprint("ab", "c") != fingerprint("a", "bc")


def test_separator_inside_a_value_is_escaped():
    assert fingerprint("a\x1fb") != fingerprint("a", "b")


def test_type_matters():
    assert fingerprint(1) != fingerprint("1")
    assert fingerprint(1) != fingerprint(1.0)


def test_path_and_string_agree():
    assert fingerprint(Path("data/03.jpg")) == fingerprint("data/03.jpg")


def test_bytes_differ_from_text():
    assert fingerprint(b"abc") != fingerprint("abc")


def test_handles_chinese_text():
    assert fingerprint("跨页") == fingerprint("跨页")
    assert fingerprint("跨页") != fingerprint("单页")


def test_handles_none_and_no_arguments():
    assert len(fingerprint(None)) == 16
    assert fingerprint() != fingerprint("")


def test_file_fingerprint_ignores_the_path(tmp_path):
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    first.write_bytes(b"page")
    second.write_bytes(b"page")
    assert file_fingerprint(first) == file_fingerprint(second)


def test_file_fingerprint_follows_the_content(tmp_path):
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    first.write_bytes(b"page")
    second.write_bytes(b"pagf")
    assert file_fingerprint(first) != file_fingerprint(second)


def test_file_fingerprint_reads_every_chunk(tmp_path):
    data = b"x" * (3 << 20)
    path = tmp_path / "big.bin"
    path.write_bytes(data)
    assert file_fingerprint(path) == hashlib.sha256(data).hexdigest()[:16]


def test_file_fingerprint_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        file_fingerprint(tmp_path / "absent.jpg")
