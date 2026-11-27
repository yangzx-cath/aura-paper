import hashlib
import re
from pathlib import Path
from threading import Thread

import pytest
from aura_paper.store.cache import Cache, file_fingerprint, fingerprint


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


NS = "understand/book"


def make_cache(tmp_path, **kwargs):
    return Cache(tmp_path / "cache", **kwargs)


def test_path_builds_namespace_and_key(tmp_path):
    cache = make_cache(tmp_path)
    path = cache.path(NS, "page_03", "abc")
    assert path == tmp_path / "cache" / NS / "page_03-abc.json"


def test_root_is_resolved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = Cache("cache")
    assert cache.root == (tmp_path / "cache").resolve()


def test_missing_entry_counts_as_miss(tmp_path):
    cache = make_cache(tmp_path)
    assert cache.load_json(NS, "page_03", "abc") is None
    assert cache.stats() == {"hit": 0, "miss": 1}


def test_saved_entry_is_returned(tmp_path):
    cache = make_cache(tmp_path)
    cache.save_json(NS, "page_03", "abc", {"标题": "小蝴蝶"})
    assert cache.load_json(NS, "page_03", "abc") == {"标题": "小蝴蝶"}
    assert cache.stats() == {"hit": 1, "miss": 0}


def test_save_json_returns_the_path(tmp_path):
    cache = make_cache(tmp_path)
    written = cache.save_json(NS, "page_03", "abc", {"a": 1})
    assert written == cache.path(NS, "page_03", "abc")
    assert written.is_file()


def test_save_keeps_chinese_readable(tmp_path):
    cache = make_cache(tmp_path)
    path = cache.save_json(NS, "page_03", "abc", {"标题": "小蝴蝶"})
    assert "小蝴蝶" in path.read_text(encoding="utf-8")


def test_has_reports_existence(tmp_path):
    cache = make_cache(tmp_path)
    assert cache.has(NS, "page_03", "abc") is False
    cache.save_json(NS, "page_03", "abc", {"a": 1})
    assert cache.has(NS, "page_03", "abc") is True


def test_has_does_not_touch_stats(tmp_path):
    cache = make_cache(tmp_path)
    cache.has(NS, "page_03", "abc")
    assert cache.stats() == {"hit": 0, "miss": 0}


def test_broken_file_counts_as_miss(tmp_path):
    cache = make_cache(tmp_path)
    path = cache.path(NS, "page_03", "abc")
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    assert cache.load_json(NS, "page_03", "abc") is None
    assert cache.stats() == {"hit": 0, "miss": 1}


def test_non_dict_file_counts_as_miss(tmp_path):
    cache = make_cache(tmp_path)
    path = cache.path(NS, "page_03", "abc")
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2]", encoding="utf-8")
    assert cache.load_json(NS, "page_03", "abc") is None
    assert cache.stats() == {"hit": 0, "miss": 1}


def test_disabled_cache_reads_nothing(tmp_path):
    cache = make_cache(tmp_path, enabled=False)
    cache.save_json(NS, "page_03", "abc", {"a": 1})
    assert cache.load_json(NS, "page_03", "abc") is None
    assert cache.has(NS, "page_03", "abc") is False


def test_disabled_cache_writes_nothing(tmp_path):
    cache = make_cache(tmp_path, enabled=False)
    written = cache.save_json(NS, "page_03", "abc", {"a": 1})
    assert written == cache.path(NS, "page_03", "abc")
    assert not (tmp_path / "cache").exists()


def test_save_leaves_no_temp_file(tmp_path):
    cache = make_cache(tmp_path)
    path = cache.save_json(NS, "page_03", "abc", {"a": 1})
    assert list(path.parent.glob("*.tmp")) == []


def test_clear_removes_one_namespace(tmp_path):
    cache = make_cache(tmp_path)
    cache.save_json(NS, "page_03", "abc", {"a": 1})
    cache.save_json("tts/book", "page_03", "def", {"b": 2})
    assert cache.clear(NS) == 1
    assert cache.has(NS, "page_03", "abc") is False
    assert cache.has("tts/book", "page_03", "def") is True


def test_clear_removes_everything(tmp_path):
    cache = make_cache(tmp_path)
    cache.save_json(NS, "page_03", "abc", {"a": 1})
    cache.save_json("tts/book", "page_03", "def", {"b": 2})
    assert cache.clear() == 2
    assert not (tmp_path / "cache").exists()


def test_clear_on_missing_root_returns_zero(tmp_path):
    cache = make_cache(tmp_path)
    assert cache.clear() == 0


def test_stats_is_a_copy(tmp_path):
    cache = make_cache(tmp_path)
    cache.load_json(NS, "page_03", "abc")
    snapshot = cache.stats()
    snapshot["miss"] = 99
    assert cache.stats()["miss"] == 1


def test_counts_stay_correct_under_threads(tmp_path):
    cache = make_cache(tmp_path)
    cache.save_json(NS, "page_03", "abc", {"a": 1})

    def read():
        for _ in range(50):
            cache.load_json(NS, "page_03", "abc")

    threads = [Thread(target=read) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert cache.stats() == {"hit": 200, "miss": 0}
