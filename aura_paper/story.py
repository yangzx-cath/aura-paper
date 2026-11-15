"""Extract the narrative structure of a whole book."""

from dataclasses import dataclass, field

from .cache import Cache, fingerprint
from .llm import LLMClient, LLMError, extract_json
from .prompts import story_prompt
from .understand import BookContent


@dataclass
class Story:
    """Narrative structure of a whole book."""

    characters: list[str] = field(default_factory=list)
    setting: str = ""
    style: str = ""
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
    """Build the narrative structure from the parsed book content."""
    prompt = story_prompt(content)
    story = Story(model=client.model)

    if cache is None:
        return _request_story(story, client, prompt, content)

    ns = f"story/{content.id}"
    key = fingerprint(prompt, client.model)

    entry = cache.load_json(ns, "book", key)
    if entry is not None:
        _apply_story(story, entry)
        return story

    story = _request_story(story, client, prompt, content)
    # Errors are never cached, so a malformed story is retried next run.
    if not story.error:
        cache.save_json(ns, "book", key, _story_fields(story))
    return story


# Call the model for the whole book and fill the story fields.
def _request_story(
    story: Story,
    client: LLMClient,
    prompt: str,
    content: BookContent,
) -> Story:
    try:
        reply = client.chat(prompt)
        fields = extract_json(reply)
    except (LLMError, ValueError) as exc:
        story.error = str(exc)
        return story

    _apply_story(story, fields)
    if len(story.beats) != content.page_count:
        expected = content.page_count
        story.error = f"expected {expected} beats, got {len(story.beats)}"
    elif not story.summary:
        story.error = "model returned no summary"
    return story


# Copy the story fields, ignoring missing or malformed values.
def _apply_story(story: Story, fields: dict) -> None:
    story.characters = _text_list(fields.get("characters"))
    story.setting = fields.get("setting", "") or ""
    story.style = fields.get("style", "") or ""
    story.summary = fields.get("summary", "") or ""
    story.beats = _text_list(fields.get("beats"))


# Turn a list from the model reply into strings, dropping empty entries.
def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


# Keep only what the model produced, so the cache holds no book identity.
def _story_fields(story: Story) -> dict:
    return {
        "characters": story.characters,
        "setting": story.setting,
        "style": story.style,
        "summary": story.summary,
        "beats": story.beats,
    }
