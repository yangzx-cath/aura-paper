import os
from pathlib import Path

import pytest

from aura_paper import config


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    # A copy keeps load_env writes out of the real environment.
    monkeypatch.setattr(os, "environ", dict(os.environ))


def write_env(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_env_reads_pairs(tmp_path):
    env_file = write_env(tmp_path, "AURA_TEST_KEY=value\n")

    config.load_env(env_file)

    assert os.environ["AURA_TEST_KEY"] == "value"


def test_load_env_keeps_existing_value(tmp_path):
    os.environ["AURA_TEST_KEY"] = "shell"
    env_file = write_env(tmp_path, "AURA_TEST_KEY=file\n")

    config.load_env(env_file)

    assert os.environ["AURA_TEST_KEY"] == "shell"


def test_load_env_skips_noise_and_strips_quotes(tmp_path):
    text = "# comment\n\nnot a pair\nAURA_TEST_KEY = 'quoted'\n"
    env_file = write_env(tmp_path, text)

    config.load_env(env_file)

    assert os.environ["AURA_TEST_KEY"] == "quoted"
    assert "not a pair" not in os.environ


def test_load_env_ignores_missing_file(tmp_path):
    config.load_env(tmp_path / "absent.env")

    assert "AURA_TEST_KEY" not in os.environ


def test_load_env_defaults_to_cwd(tmp_path, monkeypatch):
    write_env(tmp_path, "AURA_TEST_KEY=here\n")
    monkeypatch.chdir(tmp_path)

    config.load_env()

    assert os.environ["AURA_TEST_KEY"] == "here"


def test_the_storage_root_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("AURA_STORAGE", raising=False)
    monkeypatch.chdir(tmp_path)

    assert config.storage_root() == tmp_path / "storage"


def test_the_storage_root_expands_a_tilde(monkeypatch):
    monkeypatch.setenv("AURA_STORAGE", "~/data")

    assert config.storage_root() == Path.home() / "data"


def test_directories_default_under_the_storage_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_STORAGE", str(tmp_path))

    assert config.books_dir() == tmp_path / "books"
    assert config.cache_root() == tmp_path / "cache"
    assert config.output_root() == tmp_path / "output"


def test_each_directory_takes_its_own_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_BOOKS_DIR", str(tmp_path / "mine"))
    monkeypatch.setenv("AURA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("AURA_OUTPUT_DIR", str(tmp_path / "out"))

    assert config.books_dir() == tmp_path / "mine"
    assert config.cache_root() == tmp_path / "cache"
    assert config.output_root() == tmp_path / "out"


def test_directories_are_not_created(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_STORAGE", str(tmp_path))
    monkeypatch.delenv("AURA_BOOKS_DIR", raising=False)
    monkeypatch.delenv("AURA_CACHE_DIR", raising=False)
    monkeypatch.delenv("AURA_OUTPUT_DIR", raising=False)

    config.books_dir()
    config.cache_root()
    config.output_root()

    assert list(tmp_path.iterdir()) == []
