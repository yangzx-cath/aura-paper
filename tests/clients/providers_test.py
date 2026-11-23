import pytest

from aura_paper.clients.minimax import MiniMaxClient
from aura_paper.clients.providers import make_video_client
from aura_paper.clients.seedance import SeedanceClient


def test_seedance_is_the_default(monkeypatch):
    monkeypatch.delenv("AURA_VIDEO_PROVIDER", raising=False)

    assert isinstance(make_video_client(), SeedanceClient)


def test_env_selects_minimax(monkeypatch):
    monkeypatch.setenv("AURA_VIDEO_PROVIDER", "minimax")

    assert isinstance(make_video_client(), MiniMaxClient)


def test_the_argument_overrides_the_env(monkeypatch):
    monkeypatch.setenv("AURA_VIDEO_PROVIDER", "minimax")

    assert isinstance(make_video_client("seedance"), SeedanceClient)


def test_an_unknown_provider_raises(monkeypatch):
    monkeypatch.delenv("AURA_VIDEO_PROVIDER", raising=False)

    with pytest.raises(ValueError, match="unknown video provider"):
        make_video_client("other")
