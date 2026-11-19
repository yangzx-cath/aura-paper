"""Prompt that reads one page into structured content."""

from __future__ import annotations

from .layout import reading_note

# A closed set keeps mood usable for music and tone mapping.
MOOD_WORDS = (
    "好奇、欢快、兴奋、惊喜、温暖、平静、期待、担忧、害怕、生气、失落、悲伤"
)

TEMPLATE = """你是一名儿童绘本内容理解助手。

请阅读这一页绘本，严格按下面的 JSON 结构输出：

{
  "page_text": "属于故事本身的印刷文字，逐字转录，没有时留空字符串",
  "footer": "不属于故事的印刷文字，逐字转录，没有时留空字符串",
  "description": "必填，2-4 句话描述画面：地点、可见人物/物体、动作、氛围，不要复述页面文字",
  "mood": "本页情绪，从词表中选一个：__MOODS__",
  "mood_detail": "词表不贴切时的补充说明，不超过 12 个字，贴切时留空字符串"
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，五个字段都要出现，description 不能为空。
2. 除 page_text 和 footer 外，其余内容使用中文；这两个字段保留原文语言。
3. page_text 只放讲给孩子听的故事文字：角色对白、拟声词、叙述句。没有就留空字符串。
   海报标题、招牌、标签、价签等画面道具文字，放 footer。
   无字页、局部画面或大面积留白的页面，也要在 description 写清可见内容。
4. footer 放所有不属于故事的印刷文字，没有就留空字符串：
   书名、副标题、作者、译者、出版社、ISBN、定价、条形码、页码、水印，
   以及阅读指导、亲子共读提示、提问、导读等写给大人的内容。
5. page_text 和 footer 都必须逐字转录画面上印刷的文字，保留原有标点与换行，
   用 \\n 表示换行，不要改写，也不要合并两处文字。
6. 无字页很常见。没有故事文字时 page_text 必须是空字符串；不要把画面内容改写成
   page_text，例如不能把"小鸡在走路"写成"小鸡走着走着"。
7. mood 必须严格从词表中选一个。贴切时 mood_detail 留空；都不贴切时选最接近的一个，
   并把真实感受写进 mood_detail。
8. 画面中看不到的信息不要编造。只出现手、脚、背影等局部时，不要判断是谁，也不要
   写角色名或"我"；写清可见的部位、肤色、衣袖、饰品、动作、物品和位置，留给后续
   结合上下文判断。局部有机器结构、明显服装等特征时照实写出来，但不要替它命名。
9. __LAYOUT__
"""


def page_prompt(kind: str = "portrait") -> str:
    """Build the prompt for one page, aware of the page shape."""
    prompt = TEMPLATE.replace("__LAYOUT__", reading_note(kind))
    return prompt.replace("__MOODS__", MOOD_WORDS)
