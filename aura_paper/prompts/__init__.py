"""Prompt builders, one module for each kind of model call."""

from .clip_prompt import clip_prompt
from .cover_prompt import cover_prompt
from .page_prompt import page_prompt
from .screenplay_prompt import screenplay_prompt
from .split_prompt import split_prompt
from .story_prompt import story_prompt

__all__ = [
    "clip_prompt",
    "cover_prompt",
    "page_prompt",
    "screenplay_prompt",
    "split_prompt",
    "story_prompt",
]
