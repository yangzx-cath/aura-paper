"""Prompt that picks the things a child can tap in the film."""

from __future__ import annotations

from ..schema.cast import BookCast
from ..schema.publish import PublishPage

TEMPLATE = """你正在为一本儿童绘本做「点一点」问答。

孩子会在视频画面上点一个东西，系统要认出它，再把一段介绍读给孩子听。
现在先定下两件事：哪些东西值得点，以及每样东西该怎么介绍。

【书名】
__TITLE__

【角色】
__CAST__

【逐页内容】
__PAGES__

【收什么】
1. 只收故事里反复出现、或者台词与画面描述里具体讲过的。只露一面、谁也没提
   过它的，不要收——孩子点出来也给不了他任何新东西。
2. 同一件东西出现在多页，合并成一条，pages 写出现过的页码，封面是第 0 页。
3. 角色也要收，kind 写「角色」，name 用书里给它的名字。
4. 动物的习性、反复出现的说法这类知识本身就可以是一条，kind 写「知识点」。
   name 写孩子会去点的那个东西，如「小狗摇尾巴」。

【intro】
5. intro 是最终给孩子看的文字，也会原样朗读，所以按说出来的话来写：
   两到三句，四十字到八十字，说清它长什么样、有什么用、在故事里发生了什么。
6. 用口语和短句。不用成语，不写「本页」「图中」这类字眼，不用括号补充。
7. 只用上面给的文字里有的内容，不要编造故事里没有的情节。

【visual】
8. visual 是给另一个认图模型看的，写形状、颜色、大小、位置，二十字以内。
   不写情节，不写感受。

【输出】
9. 只输出 JSON，不用代码块，不加解释。
10. kind 只能是：角色、道具、场景、知识点。
11. 没有值得点的东西就输出 {"topics": []}。

{
  "topics": [
    {
      "name": "积木城堡",
      "kind": "道具",
      "aliases": ["城堡", "积木"],
      "visual": "彩色积木叠成的塔，一层比一层小",
      "intro": "花花和小满一起搭的积木城堡，一块一块往上叠。搭到第九层的时候，城堡晃了晃，整座倒了下来。",
      "pages": [1, 2, 3, 4]
    }
  ]
}
"""


def topic_prompt(title: str, cast: BookCast, pages: list[PublishPage]) -> str:
    """Build the prompt that picks the things a child can tap."""
    text = TEMPLATE.replace("__TITLE__", title or "（没有书名）")
    text = text.replace("__CAST__", _cast_text(cast))
    return text.replace("__PAGES__", _pages_text(pages))


# Name every character, with the look the understand stage wrote for it.
def _cast_text(cast: BookCast) -> str:
    lines = []
    for member in cast.cast:
        if not member.name:
            continue
        line = f"{member.name}：{member.look}" if member.look else member.name
        lines.append(line)
    return "\n".join(lines) or "（没有角色）"


# One line per page: what it says, what it shows and who is on it.
def _pages_text(pages: list[PublishPage]) -> str:
    lines = []
    for page in pages:
        said = page.text.replace("\n", " ").strip() or "（无台词）"
        drawn = page.desc.strip() or "（无画面描述）"
        names = "、".join(page.cast)
        tail = f"｜出现：{names}" if names else ""
        lines.append(f"第 {page.page} 页：{said}｜画面：{drawn}{tail}")
    return "\n".join(lines) or "（没有页面）"
