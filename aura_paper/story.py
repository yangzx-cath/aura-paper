"""Extract the narrative structure of a whole book."""

from dataclasses import dataclass, field

from .cache import Cache
from .llm import LLMClient
from .understand import BookContent


@dataclass
class Story:
    """Narrative structure of a whole book."""

    characters: list[str] = field(default_factory=list)
    summary: str = ""
    beats: list[str] = field(default_factory=list)
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this story."""
        raise NotImplementedError("Story.to_dict")


def build_story(
    content: BookContent,
    client: LLMClient,
    *,
    cache: Cache | None = None,
) -> Story:
    """Read the whole book and return its narrative structure."""
    raise NotImplementedError("build_story")
