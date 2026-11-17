"""Derive the story context shared by every page of a book."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .cache import Cache, fingerprint
from .llm import LLMClient, LLMError
from .output import write_json
from .prompts import story_prompt
from .understand import BookContent
from .utils import extract_json, now_iso


@dataclass
class Cast:
    """One character with the look that keeps pages consistent."""

    name: str
    look: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this character."""
        return {"name": self.name, "look": self.look}

    @classmethod
    def from_dict(cls, data: dict) -> Cast:
        """Build a character from its external JSON shape."""
        return cls(
            name=str(data.get("name") or ""),
            look=str(data.get("look") or ""),
        )


@dataclass
class Story:
    """Story context shared by every page."""

    id: str = ""
    characters: list[str] = field(default_factory=list)
    cast: list[Cast] = field(default_factory=list)
    setting: str = ""
    style: str = ""
    summary: str = ""
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this story."""
        return {
            "id": self.id,
            "generated_at": now_iso(),
            "model": self.model,
            "characters": self.characters,
            "cast": [member.to_dict() for member in self.cast],
            "setting": self.setting,
            "style": self.style,
            "summary": self.summary,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Story:
        """Build a story from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            characters=_text_list(data.get("characters")),
            cast=_cast_list(data.get("cast")),
            setting=str(data.get("setting") or ""),
            style=str(data.get("style") or ""),
            summary=str(data.get("summary") or ""),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


# Turn a list from the model reply into strings, dropping empty entries.
def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


# Read the cast list, dropping entries that carry no name.
def _cast_list(value: object) -> list[Cast]:
    if not isinstance(value, list):
        return []
    members = [
        Cast.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [member for member in members if member.name]


def build_story(
    content: BookContent,
    client: LLMClient,
    *,
    cache: Cache | None = None,
) -> Story:
    """Derive the story context from the parsed book content."""
    prompt = story_prompt(content)
    story = Story(id=content.id, model=client.model)

    if cache is None:
        return _request_story(story, client, prompt)

    ns = f"story/{content.id}"
    key = fingerprint(prompt, client.model)

    entry = cache.load_json(ns, "story", key)
    if entry is not None:
        _apply_story(story, entry)
        return story

    story = _request_story(story, client, prompt)
    # Errors are never cached, so a malformed story is retried next run.
    if not story.error:
        cache.save_json(ns, "story", key, _story_fields(story))
    return story


# Call the model for the whole book and fill the story fields.
def _request_story(
    story: Story,
    client: LLMClient,
    prompt: str,
) -> Story:
    try:
        reply = client.chat(prompt)
        fields = extract_json(reply)
    except (LLMError, ValueError) as exc:
        story.error = str(exc)
        return story

    _apply_story(story, fields)
    if not story.summary:
        story.error = "model returned no summary"
    return story


# Copy the story fields, ignoring missing or malformed values.
def _apply_story(story: Story, fields: dict) -> None:
    story.characters = _text_list(fields.get("characters"))
    story.cast = _cast_list(fields.get("cast"))
    story.setting = str(fields.get("setting") or "")
    story.style = str(fields.get("style") or "")
    story.summary = str(fields.get("summary") or "")


# Keep only what the model produced, so the cache holds no book identity.
def _story_fields(story: Story) -> dict:
    return {
        "characters": story.characters,
        "cast": [member.to_dict() for member in story.cast],
        "setting": story.setting,
        "style": story.style,
        "summary": story.summary,
    }


def save_story(
    story: Story,
    root: str | Path | None = None,
) -> Path:
    """Write the story to <root>/<id>/story.json."""
    return write_json(story.id, "story", story.to_dict(), root)
