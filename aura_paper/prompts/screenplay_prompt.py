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

本页 uncertain：
__UNCERTAIN__

本页 resolved：
__RESOLVED__

本页 unresolved：
__UNRESOLVED__

只输出 JSON，不要解释，不要用代码块；两个字段都要有：
{
  "beat": "这一页看得见的新变化，20-30 字",
  "lines": [
    {"kind": "narration", "speaker": "", "text": "旁白"},
    {"kind": "dialogue", "speaker": "角色名", "text": "对白"}
  ]
}

规则：
1. beat 用中文，写“谁做了什么、结果或情绪怎么变”，20-30 字。不要写镜头运动、
   转场，也不要写“铺垫、承接、形成结尾”等编辑语；写动作和变化，不要只复述画面。
   画面没有明显动作时，写角色最明显的动作或反应，不编新情节。
2. lines 用__LANGUAGE__，按播放顺序排列。每条要完整自然、能单独听懂；可把一句
   原文拆成几条短句，但不要把两句合并。用 4-12 岁孩子听得懂的话，避免长从句、
   插入语和连续重复的句式。
3. kind 只用 narration 或 dialogue。只有“文字”中引号里的原话才是 dialogue；
   引号外的第一人称、心理活动和普通叙述都是 narration，speaker 留空。
4. dialogue 必须照抄引号里的原话，去掉引号和“他说、她问、I say、he says, smiling”
   等说明文字；说明文字需要时另写 narration。
   例：原文 “Kuan can buy it,” he says, smiling. → dialogue 为 Kuan can buy it，
   speaker 为 Dad。
5. narration 用来读“文字”里的叙述句，或连接页面、交代画面里看得见的动作；
   无字页可返回空 lines。不编原文没有的情节、关系、身份或姓名；画面里未被文字
   提到的人，只写动作，不给称呼。
6. 局部画面例外：画面只描述手、脚、背影时，结合 resolved、全书角色、外形和
   上一页内容判断是谁；能判断就用角色名或“我”，不能判断就只写动作，不硬猜。
7. speaker 只用全书角色或“我”；说话人不在角色表里时不要猜名字，把原话写成
   narration。叙述者是“我”时，旁白用 I，不要写 the child、the boy、the girl。
8. 不要重复上一页的 beat 或台词，角色称呼前后一致。
9. 只输出能确定的内容。resolved 的结论可以直接使用；unresolved，以及 uncertain
   中没有 resolved 结论的项，都不要写进 beat 或 lines，也不要猜。信息不足时只写
   看得见的动作，必要时返回空 lines。
10. 输出前自检：beat 无镜头/编辑语；dialogue 只来自引号；引号外第一人称都是
    narration；每条 line 自然完整；没有把 unresolved 写成确定内容。
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
    prompt = prompt.replace("__UNCERTAIN__", _uncertain_text(page))
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


# Render the page uncertainty list, or a placeholder when there is none.
def _uncertain_text(page: PageContent) -> str:
    return "\n".join(f"- {item}" for item in page.uncertain) or "（无）"


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
