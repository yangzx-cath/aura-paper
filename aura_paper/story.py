"""Derive the story context shared by every page of a book."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .cache import Cache, fingerprint
from .llm import LLMClient, LLMError
from .output import write_json
from .prompts1 import story_prompt
from .understand import BookContent, PageContent
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
class Reference:
    """The figure chosen to show one character's look."""

    name: str
    page: int
    figure: int = -1
    why: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this reference."""
        return {
            "name": self.name,
            "page": self.page,
            "figure": self.figure,
            "why": self.why,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Reference:
        """Build a reference from its external JSON shape."""
        return cls(
            name=str(data.get("name") or ""),
            page=_int_value(data.get("page"), 0),
            figure=_int_value(data.get("figure"), -1),
            why=str(data.get("why") or ""),
        )


@dataclass
class PageCast:
    """The cast members the story stage placed on one page."""

    page: int
    names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the external JSON shape of this page cast."""
        return {"page": self.page, "names": self.names}

    @classmethod
    def from_dict(cls, data: dict) -> PageCast:
        """Build a page cast from its external JSON shape."""
        return cls(
            page=_int_value(data.get("page"), 0),
            names=_text_list(data.get("names")),
        )


@dataclass
class Resolution:
    """One page uncertainty resolved or left open by the story stage."""

    index: int
    issue: str
    answer: str = ""
    evidence: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        """Return the external JSON shape of this resolution."""
        return {
            "index": self.index,
            "issue": self.issue,
            "answer": self.answer,
            "evidence": self.evidence,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Resolution:
        """Build a resolution from its external JSON shape."""
        return cls(
            index=int(data.get("index") or 0),
            issue=str(data.get("issue") or ""),
            answer=str(data.get("answer") or ""),
            evidence=str(data.get("evidence") or ""),
            reason=str(data.get("reason") or ""),
        )


@dataclass
class Story:
    """Story context shared by every page."""

    id: str = ""
    characters: list[str] = field(default_factory=list)
    cast: list[Cast] = field(default_factory=list)
    on_page: list[PageCast] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    setting: str = ""
    style: str = ""
    summary: str = ""
    resolved: list[Resolution] = field(default_factory=list)
    unresolved: list[Resolution] = field(default_factory=list)
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
            "on_page": [item.to_dict() for item in self.on_page],
            "references": [item.to_dict() for item in self.references],
            "setting": self.setting,
            "style": self.style,
            "summary": self.summary,
            "resolved": [item.to_dict() for item in self.resolved],
            "unresolved": [item.to_dict() for item in self.unresolved],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Story:
        """Build a story from its external JSON shape."""
        return cls(
            id=str(data.get("id") or ""),
            characters=_text_list(data.get("characters")),
            cast=_cast_list(data.get("cast")),
            on_page=_page_list(data.get("on_page")),
            references=_reference_list(data.get("references")),
            setting=str(data.get("setting") or ""),
            style=str(data.get("style") or ""),
            summary=str(data.get("summary") or ""),
            resolved=_resolution_list(data.get("resolved")),
            unresolved=_resolution_list(data.get("unresolved")),
            model=str(data.get("model") or ""),
            error=str(data.get("error") or ""),
        )


# Read an integer, falling back to the default when the value is unusable.
def _int_value(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


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


# Read reference entries, keeping the first figure chosen for each character.
def _reference_list(value: object) -> list[Reference]:
    if not isinstance(value, list):
        return []
    items = [
        Reference.from_dict(item) for item in value if isinstance(item, dict)
    ]
    picked: dict[str, Reference] = {}
    for item in items:
        if item.name and item.page > 0 and item.figure >= 0:
            picked.setdefault(item.name, item)
    return list(picked.values())


# Read page cast entries, keeping the first entry for each page.
def _page_list(value: object) -> list[PageCast]:
    if not isinstance(value, list):
        return []
    picked: dict[int, PageCast] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        entry = PageCast.from_dict(item)
        names = list(dict.fromkeys(name for name in entry.names if name))
        if names and entry.page > 0:
            picked.setdefault(entry.page, PageCast(entry.page, names))
    return list(picked.values())


# Read resolution entries, dropping entries that carry no issue.
def _resolution_list(value: object) -> list[Resolution]:
    if not isinstance(value, list):
        return []
    items = [
        Resolution.from_dict(item) for item in value if isinstance(item, dict)
    ]
    return [item for item in items if item.issue]


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
        return _keep_known(_request_story(story, client, prompt), content)

    ns = f"story/{content.id}"
    key = fingerprint(prompt, *client.signature)

    entry = cache.load_json(ns, "story", key)
    if entry is not None:
        _apply_story(story, entry)
        return _keep_known(story, content)

    story = _keep_known(_request_story(story, client, prompt), content)
    # Errors are never cached, so a malformed story is retried next run.
    if not story.error:
        cache.save_json(ns, "story", key, _story_fields(story))
    return story


# Drop page and figure pointers that the book cannot satisfy.
def _keep_known(story: Story, content: BookContent) -> Story:
    pages = {page.index: page for page in content.pages}
    story.on_page = [item for item in story.on_page if item.page in pages]
    story.references = [
        item
        for item in story.references
        if _has_figure(pages, item.page, item.figure)
    ]
    return story


# Check that a page holds a figure at the given number.
def _has_figure(pages: dict[int, PageContent], page: int, figure: int) -> bool:
    found = pages.get(page)
    return found is not None and 0 <= figure < len(found.figures)


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
    story.on_page = [
        PageCast(item.page, [n for n in item.names if n in story.characters])
        for item in _page_list(fields.get("on_page"))
    ]
    story.on_page = [item for item in story.on_page if item.names]
    story.references = [
        item
        for item in _reference_list(fields.get("references"))
        if item.name in story.characters
    ]
    story.setting = str(fields.get("setting") or "")
    story.style = str(fields.get("style") or "")
    story.summary = str(fields.get("summary") or "")
    story.resolved = _resolution_list(fields.get("resolved"))
    story.unresolved = _resolution_list(fields.get("unresolved"))


# Keep only what the model produced, so the cache holds no book identity.
def _story_fields(story: Story) -> dict:
    return {
        "characters": story.characters,
        "cast": [member.to_dict() for member in story.cast],
        "on_page": [item.to_dict() for item in story.on_page],
        "references": [item.to_dict() for item in story.references],
        "setting": story.setting,
        "style": story.style,
        "summary": story.summary,
        "resolved": [item.to_dict() for item in story.resolved],
        "unresolved": [item.to_dict() for item in story.unresolved],
    }


def save_story(
    story: Story,
    root: str | Path | None = None,
) -> Path:
    """Write the story to <root>/<id>/story.json."""
    return write_json(story.id, "story", story.to_dict(), root)
