"""Prompt that turns one page into a video clip request."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..story import Story
    from ..understand import PageContent

TEMPLATE = """你是一名儿童绘本动画分镜师。

请把这一页绘本画面制作成一段连贯的动画。提供的原图只作为参考，不作为视频起始帧。

故事背景：
- 角色：__CHARACTERS__
- 地点：__SETTING__
- 画风：__STYLE__
- 全书主线：__SUMMARY__

本页分镜：
- 页码：第 __INDEX__ 页
- 剧情：__BEAT__
- 画面：__DESCRIPTION__
- 情绪：__MOOD__

要求：
1. 原图只用于参考角色造型、画风、配色和构图；只表现本页画面内容，不新增角色，
   不改变角色造型、服装和画面风格。
2. 画面中不要出现文字、字幕、水印或边框。
3. 动作自然、幅度适中，适合儿童观看，避免剧烈晃动、快速变焦和恐怖画面。
4. 镜头运动克制，不切换场景；竖幅使用 [Push in] 缓慢推进，横幅从左到右缓慢平移。
5. 剧情提示只表现本页画面里的动作；不添加原文没有的情节，不描述画面外的内容。
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
    prompt = prompt.replace("__SUMMARY__", story.summary or "（未提供）")
    prompt = prompt.replace("__INDEX__", str(page.index))
    prompt = prompt.replace("__BEAT__", beat.strip() or "（按画面自然动作）")
    prompt = prompt.replace(
        "__DESCRIPTION__", page.description or "（未提供）"
    )
    return prompt.replace("__MOOD__", page.mood or "（未提供）")
