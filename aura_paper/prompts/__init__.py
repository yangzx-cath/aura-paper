"""Prompt builders, one module for each kind of model call."""

from __future__ import annotations

from .cover import cover_prompt
from .page import page_prompt
from .screenplay import screenplay_prompt
from .shot import shot_prompt
from .split import split_prompt
from .story import story_prompt

__all__ = [
    "cover_prompt",
    "page_prompt",
    "screenplay_prompt",
    "shot_prompt",
    "split_prompt",
    "story_prompt",
]
