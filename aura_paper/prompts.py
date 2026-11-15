"""
Prompt templates for model calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .understand import BookContent

_LAYOUT_NOTES = {
    "single": "这是一页单页画面。",
    "spread": "这是一张跨页画面，包含左右两页，请按从左到右的顺序阅读和描述画面。",
}

# A closed set keeps mood usable for music and tone mapping.
_MOOD_WORDS = (
    "好奇、欢快、兴奋、惊喜、温暖、平静、期待、担忧、害怕、生气、失落、悲伤"
)

_PAGE_TEMPLATE = """你是一名儿童绘本内容理解助手。

请阅读这一页绘本，严格按下面的 JSON 结构输出：

{
  "page_text": "画面上印刷文字的逐字转录，没有文字时留空字符串",
  "description": "用 2-4 句话描述画面：地点、角色、动作、氛围，不要复述页面文字",
  "mood": "本页情绪，从词表中选一个：__MOODS__",
  "mood_detail": "词表不贴切时的补充说明，不超过 12 个字，贴切时留空字符串"
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，四个字段都要出现。
2. 除 page_text 外，其余内容使用中文；page_text 保留原文语言。
3. page_text 只能逐字转录画面上印刷的文字，保留原有标点与换行，用 \\n 表示换行。
4. 无字页很常见。画面没有印刷文字时 page_text 必须是空字符串，也不能把画面改写成句子，例如不能把"小鸡在走路"写成"小鸡走着走着"。
5. mood 必须严格从词表中选一个。贴切时 mood_detail 留空字符串，都不贴切时选最接近的一个，并把真实感受写进 mood_detail。
6. 画面中看不到的信息不要编造。
7. __LAYOUT__
"""


def page_prompt(kind: str = "single") -> str:
    """Build the prompt for one page, aware of single or spread layout."""
    note = _LAYOUT_NOTES.get(kind, _LAYOUT_NOTES["single"])
    prompt = _PAGE_TEMPLATE.replace("__LAYOUT__", note)
    return prompt.replace("__MOODS__", _MOOD_WORDS)


_STORY_TEMPLATE = """你是一名儿童绘本的编剧助手。

下面是一本绘本逐页的内容，共 __COUNT__ 页。

__PAGES__

请通读全书，严格按下面的 JSON 结构输出：

{
  "characters": ["主要角色，用书中出现的称呼"],
  "setting": "故事发生的地点与环境，不超过 20 字",
  "style": "画面风格关键词，不超过 20 字",
  "summary": "全书主线，100-200 字",
  "beats": ["第 1 页的情节推进", "第 2 页的情节推进"]
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，五个字段都要出现。
2. 所有内容使用中文，角色名除外。
3. characters 用书中最正式的称呼，例如"小鸡球球"而不是"小鸡"或"球球"。后续每页提到同一角色都用这个名字。
4. beats 的长度必须恰好等于 __COUNT__，按页序排列，每页一句话，20-30 字，只写这一页推进了什么，不要描述画面细节。
5. summary 概括全书主线，不添加原文没有的情节。
6. setting 和 style 要能代表全书，用于统一后续的画面生成。
"""


def story_prompt(content: BookContent) -> str:
    """Build the prompt that turns page contents into a story outline."""
    blocks = []
    for page in content.pages:
        blocks.append(
            f"第 {page.index + 1} 页\n"
            f"文字：{page.page_text or '（无字）'}\n"
            f"画面：{page.description}\n"
            f"情绪：{page.mood}"
        )

    prompt = _STORY_TEMPLATE.replace("__PAGES__", "\n\n".join(blocks))
    return prompt.replace("__COUNT__", str(content.page_count))
