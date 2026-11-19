"""Prompt builders, one module for each kind of model call."""

from .cover_prompt import cover_prompt
from .page_prompt import page_prompt
from .screenplay_prompt import screenplay_prompt
from .shot_prompt import shot_prompt
from .split_prompt import split_prompt
from .story_prompt import story_prompt

__all__ = [
    "cover_prompt",
    "page_prompt",
    "screenplay_prompt",
    "shot_prompt",
    "split_prompt",
    "story_prompt",
]
