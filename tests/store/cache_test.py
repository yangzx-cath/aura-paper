import hashlib
from pathlib import Path
from threading import Thread

import pytest

from aura_paper.store.cache import Cache, file_fingerprint, fingerprint

NAMESPACE = "understand/book"


def make_cache(tmp_path, **kwargs):
    return Cache(tmp_path / "cache", **kwargs)


class TestCache:
    def test_has_is_false_when_disabled(self, tmp_path):
        cache = make_cache(tmp_path, enabled=False)
        path = cache.path(NAMESPACE, "page_03", "abc")
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")

        assert cache.has(NAMESPACE, "page_03", "abc") is False

    def test_load_json_counts_a_broken_file_as_miss(self, tmp_path):
        cache = make_cache(tmp_path)
        path = cache.path(NAMESPACE, "page_03", "abc")
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")

        assert cache.load_json(NAMESPACE, "page_03", "abc") is None
        assert cache.stats() == {"hit": 0, "miss": 1}

    def test_load_json_counts_a_non_object_as_miss(self, tmp_path):
        cache = make_cache(tmp_path)
        path = cache.path(NAMESPACE, "page_03", "abc")
        path.parent.mkdir(parents=True)
        path.write_text("[1, 2]", encoding="utf-8")

        assert cache.load_json(NAMESPACE, "page_03", "abc") is None
        assert cache.stats() == {"hit": 0, "miss": 1}

    def test_save_json_writes_nothing_when_disabled(self, tmp_path):
        cache = make_cache(tmp_path, enabled=False)

        written = cache.save_json(NAMESPACE, "page_03", "abc", {"a": 1})

        assert written == cache.path(NAMESPACE, "page_03", "abc")
        assert not (tmp_path / "cache").exists()
        assert cache.load_json(NAMESPACE, "page_03", "abc") is None

    def test_clear_removes_only_the_named_namespace(self, tmp_path):
        cache = make_cache(tmp_path)
        cache.save_json(NAMESPACE, "page_03", "abc", {"a": 1})
        cache.save_json("tts/book", "page_03", "def", {"b": 2})

        removed = cache.clear(NAMESPACE)

        assert removed == 1
        assert cache.has(NAMESPACE, "page_03", "abc") is False
        assert cache.has("tts/book", "page_03", "def") is True

    def test_clear_without_a_namespace_empties_the_cache(self, tmp_path):
        cache = make_cache(tmp_path)
        cache.save_json(NAMESPACE, "page_03", "abc", {"a": 1})
        cache.save_json("tts/book", "page_03", "def", {"b": 2})

        removed = cache.clear()

        assert removed == 2
        assert cache.has(NAMESPACE, "page_03", "abc") is False
        assert cache.has("tts/book", "page_03", "def") is False

    def test_stats_hold_under_threads(self, tmp_path):
        cache = make_cache(tmp_path)
        cache.save_json(NAMESPACE, "page_03", "abc", {"a": 1})

        def read():
            for _ in range(50):
                cache.load_json(NAMESPACE, "page_03", "abc")

        threads = [Thread(target=read) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert cache.stats() == {"hit": 200, "miss": 0}


def test_fingerprint_ignores_dict_key_order():
    left = fingerprint({"a": 1, "b": 2})
    right = fingerprint({"b": 2, "a": 1})

    assert left == right


def test_fingerprint_keeps_list_order():
    first = fingerprint(["a", "b"])
    second = fingerprint(["b", "a"])

    assert first != second


def test_fingerprint_separates_argument_parts():
    joined = fingerprint("ab", "c")
    split = fingerprint("a", "bc")

    assert joined != split


def test_fingerprint_separates_a_separator_in_a_value():
    inside = fingerprint("a\x1fb")
    outside = fingerprint("a", "b")

    assert inside != outside


def test_fingerprint_keeps_types_apart():
    number = fingerprint(1)

    assert number != fingerprint("1")
    assert number != fingerprint(1.0)


def test_fingerprint_separates_bytes_from_text():
    assert fingerprint(b"abc") != fingerprint("abc")


def test_fingerprint_treats_a_path_as_its_text():
    assert fingerprint(Path("data/03.jpg")) == fingerprint("data/03.jpg")


def test_file_fingerprint_depends_on_content_not_path(tmp_path):
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    first.write_bytes(b"page")
    second.write_bytes(b"page")

    assert file_fingerprint(first) == file_fingerprint(second)


def test_file_fingerprint_reads_past_the_first_chunk(tmp_path):
    data = b"x" * (3 << 20)
    path = tmp_path / "big.bin"
    path.write_bytes(data)

    assert file_fingerprint(path) == hashlib.sha256(data).hexdigest()[:16]


def test_file_fingerprint_raises_when_the_file_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        file_fingerprint(tmp_path / "absent.jpg")
