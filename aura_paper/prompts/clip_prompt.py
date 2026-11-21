"""Prompt that turns one page into a video clip request."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..story import Story
    from ..understand import PageContent

TEMPLATE = """你是儿童绘本动画分镜师，把这一页做成一段连贯动画。

- 角色：__CHARACTERS__
- 地点：__SETTING__
- 画风：__STYLE__
- 剧情：__BEAT__
- 画面：__DESCRIPTION__

要求：
1. 原图只参考造型、配色和构图：不新增角色，不改服装和画风，不写画面外的情节。
2. 动作自然、幅度适中，适合儿童观看；镜头克制，不切场景。竖幅用 [Push in]
   缓慢推进，横幅从左到右缓慢平移。
3. 画面里不要出现文字、字幕、水印和边框。
"""


def clip_prompt(
    page: PageContent,
    story: Story,
    *,
    beat: str = "",
) -> str:
    """Build the video prompt for one page."""
    characters = "、".join(story.characters) or "（未提供）"

    prompt = TEMPLATE.replace("__CHARACTERS__", characters)
    prompt = prompt.replace("__SETTING__", story.setting or "（未提供）")
    prompt = prompt.replace("__STYLE__", story.style or "（未提供）")
    prompt = prompt.replace("__BEAT__", beat.strip() or "（按画面自然动作）")
    return prompt.replace("__DESCRIPTION__", page.description or "（未提供）")
