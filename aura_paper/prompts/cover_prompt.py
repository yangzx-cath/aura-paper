"""Prompt that reads the book details off the cover."""

from .layout import reading_note

TEMPLATE = """你是一名儿童绘本编辑。

请阅读这本书的封面，严格按下面的 JSON 结构输出：

{
  "title": "书名",
  "author": "作者",
  "illustrator": "绘者",
  "description": "必填，2-4 句话描述封面画面：地点、可见人物/物体、动作、氛围"
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，四个字段都要出现。
2. description 使用中文；title、author、illustrator 保留封面上的原文，不要翻译。
3. title 取封面上最大最显眼的字，去掉书名号和引号。
4. author、illustrator 按封面上的"文/著/图/绘/译"等标注区分；
   封面没写的留空字符串，不要从画面或正文推断。
5. 画面上的人物名字不是作者，封面上写的才是。
6. 画面中看不到的信息不要编造。
7. __LAYOUT__
"""


def cover_prompt(kind: str = "portrait") -> str:
    """Build the prompt that reads the book metadata off the cover."""
    return TEMPLATE.replace("__LAYOUT__", reading_note(kind))
