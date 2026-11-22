"""
Prompts for the video pipeline.
"""

from .cast_prompt import cast_prompt
from .cover_prompt import cover_prompt
from .layout_prompt import layout_prompt
from .location_prompt import location_prompt
from .page_prompt import page_prompt
from .spoken_prompt import spoken_prompt
from .storyboard_prompt import storyboard_prompt

__all__ = [
    "cast_prompt",
    "cover_prompt",
    "layout_prompt",
    "location_prompt",
    "page_prompt",
    "spoken_prompt",
    "storyboard_prompt",
]
