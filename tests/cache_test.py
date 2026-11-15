import re
from pathlib import Path

from aura_paper.cache import fingerprint


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
