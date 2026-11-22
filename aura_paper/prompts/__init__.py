"""
Prompts for the video pipeline.
"""

from .cover_prompt import cover_prompt
from .layout_prompt import layout_prompt
from .page_prompt import page_prompt

__all__ = ["cover_prompt", "layout_prompt", "page_prompt"]
