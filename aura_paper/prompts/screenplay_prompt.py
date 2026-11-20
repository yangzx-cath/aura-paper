"""Prompt that plans one page as a scene."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..story import Resolution, Story
    from ..understand import PageContent

TEMPLATE = """你是一名儿童绘本编剧。请根据全书设定和本页内容，写出这一页的分镜提示和朗读台词。

全书设定：
- 语言：__LANGUAGE__
- 角色：__CHARACTERS__
- 外形：__CAST__
- 地点：__SETTING__
- 画风：__STYLE__
- 全书主线：__SUMMARY__

上一页内容（不要重复）：
__PREVIOUS__

本页内容：
- 故事页：第 __INDEX__ 页
- 文字：__PAGE_TEXT__
- 画面：__DESCRIPTION__
- 情绪：__MOOD__

本页 resolved：
__RESOLVED__

本页 unresolved：
__UNRESOLVED__

只输出 JSON，不要解释，不要用代码块；三个字段都要有：
{
  "beat": "这一页看得见的新变化，20-30 字",
  "duration": "整数秒，取值见规则 1",
  "lines": [
    {"kind": "narration", "speaker": "", "text": "旁白"},
    {"kind": "dialogue", "speaker": "角色名", "text": "对白"}
  ]
}

规则：
beat 和 duration 用来生成视频画面，不会被念出来；lines 会被念出来。画面的事写进
beat，声音的事写进 lines。

1. beat 用中文，写“谁做了什么、结果或情绪怎么变”，20-30 字。要写这一页新增的
   变化，不是把画面重说一遍；不写镜头运动、转场，也不写“铺垫、承接、形成结尾”
   这类编辑语。画面没有明显动作时，写角色最明显的反应，不编新情节。
   duration 是整数秒，按 beat 里的动作量估，不看台词长短：一个动作 4-6 秒，
   连续动作或情绪停顿 7-10 秒，几个动作接连发生 11-15 秒。
2. lines 用__LANGUAGE__，按播放顺序排列。每条要完整自然、能单独听懂；可把一句
   原话拆成几条短句，但不要把两句合并。用 4-12 岁孩子听得懂的话，避免长从句、
   插入语和连续重复的句式。单个镜头最长 15 秒，所以全页朗读不超过 12 秒：中文约
   50 字，英文约 30 个词（不超过 144 个字母）。超了先删旁白，保留引号里的原话。
3. kind 只有 narration 和 dialogue。dialogue 只能是“文字”里引号内的原话，照抄，
   去掉引号和“他说、她问、he says, smiling”这类说明文字，说明文字需要时另写
   narration。例：“Kuan can buy it,” he says, smiling. → 原话 Kuan can buy it。
4. 引号外的话都是 narration，speaker 留空。narration 只留画面说不出的内容：书上
   的拟声词照原字念（阿嚏、哎哟），不改写成“打了个喷嚏”这类描述；再加上心理
   活动、时间推移、前因后果。原文的叙述句也按这条筛，画面已经呈现的动作、神态、
   表情、场景一律不读。筛完没剩下什么就返回空 lines，不要为了填满而读画面。
   不编原文没有的情节、关系、身份或姓名。
5. speaker 只用全书角色或“我”。画面只露手、脚、背影时，结合 resolved、角色表、
   外形和上一页内容判断是谁；判断不出就不写这个人，不硬猜。说话人不在角色表里
   时不要猜名字，把原话写成 narration。叙述者是“我”时，旁白用 I，不写 the
   child、the boy、the girl。
6. 不要重复上一页的 beat 或台词，角色称呼前后一致。
7. 只输出能确定的内容。resolved 里已给结论的，按结论写；unresolved 的每一条都
   不要写进 beat 或 lines，也不要猜。
8. 输出前自检：beat 有新增变化，且无镜头语和编辑语；duration 与动作量相称；
   dialogue 只来自引号；引号外的话都是 narration；narration 没有复述画面里看得见
   的内容；每条 line 自然完整；没有把 unresolved 写成确定内容。
"""


def screenplay_prompt(
    page: PageContent,
    story: Story,
    *,
    previous: str = "",
    language: str = "",
    resolved: list[Resolution] | None = None,
    unresolved: list[Resolution] | None = None,
) -> str:
    """Build the prompt that plans one page as a scene."""
    characters = "、".join(story.characters) or "（未提供）"
    prompt = TEMPLATE.replace("__CHARACTERS__", characters)
    prompt = prompt.replace("__LANGUAGE__", language or "原文的语言")
    prompt = prompt.replace("__CAST__", _cast_text(story))
    prompt = prompt.replace("__SETTING__", story.setting or "（未提供）")
    prompt = prompt.replace("__STYLE__", story.style or "（未提供）")
    prompt = prompt.replace("__SUMMARY__", story.summary or "（未提供）")
    prompt = prompt.replace("__PREVIOUS__", previous or "（这是第一页）")
    prompt = prompt.replace("__INDEX__", str(page.index))
    prompt = prompt.replace("__PAGE_TEXT__", page.page_text or "（无字）")
    prompt = prompt.replace(
        "__RESOLVED__", _resolution_text(resolved or [], "（无）")
    )
    prompt = prompt.replace(
        "__UNRESOLVED__", _resolution_text(unresolved or [], "（无）")
    )
    prompt = prompt.replace(
        "__DESCRIPTION__", page.description or "（未提供）"
    )
    return prompt.replace("__MOOD__", page.mood or "（未提供）")


# Render resolved or unresolved items with their evidence or reason.
def _resolution_text(
    items: list[Resolution],
    empty: str,
) -> str:
    lines = []
    for item in items:
        parts = [f"- {item.issue}"]
        if item.answer:
            parts.append(f"结论：{item.answer}")
        if item.evidence:
            parts.append(f"依据：{item.evidence}")
        if item.reason:
            parts.append(f"原因：{item.reason}")
        lines.append("；".join(parts))
    return "\n".join(lines) or empty


# Render the cast as "名字（外形）" so a scene knows how each one looks.
def _cast_text(story: Story) -> str:
    parts = []
    for member in story.cast:
        if member.look:
            parts.append(f"{member.name}（{member.look}）")
        else:
            parts.append(member.name)
    return "；".join(parts) or "（未提供）"
