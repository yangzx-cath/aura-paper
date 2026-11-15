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


def test_cache_root_prefers_env_override(tmp_path):
    os.environ["AURA_CACHE_DIR"] = str(tmp_path / "mine")
    assert config.cache_root() == tmp_path / "mine"


def test_cache_root_expands_home(tmp_path):
    os.environ["AURA_CACHE_DIR"] = "~/mine"
    assert config.cache_root() == Path.home() / "mine"


def test_cache_root_uses_xdg_cache_home(tmp_path):
    os.environ["XDG_CACHE_HOME"] = str(tmp_path / "xdg")
    expected = tmp_path / "xdg" / config.APP_NAME
    assert config.cache_root() == expected


def test_cache_root_falls_back_to_home_cache(tmp_path):
    os.environ["HOME"] = str(tmp_path)
    expected = tmp_path / ".cache" / config.APP_NAME
    assert config.cache_root() == expected


def test_out_root_prefers_env_override(tmp_path):
    os.environ["AURA_OUT_DIR"] = str(tmp_path / "mine")
    assert config.out_root() == tmp_path / "mine"


def test_out_root_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert config.out_root() == tmp_path / "out"


def test_roots_do_not_create_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.environ["AURA_CACHE_DIR"] = str(tmp_path / "cache")

    config.cache_root()
    config.out_root()

    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "out").exists()
