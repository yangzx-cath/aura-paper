"""Prompt that groups the figure crops into characters."""

from __future__ import annotations

from ..schema.assets import FigurePick
from ..schema.content import PageContent

# Words that mark an uncertainty as being about who someone is.
IDENTITY_WORDS = ("同一人", "身份", "是谁", "指谁", "名字", "对应")

TEMPLATE = """你是一名儿童绘本的角色设定助手。

下面是这本书的逐页文字和 __COUNT__ 张人物裁图。

【逐页文字】
__PAGES__

【待确认的身份疑问】
__ISSUES__

【人物裁图】
__CROPS__

请判断这本书需要哪些角色：这些裁图里有几个角色、分别是谁，每张裁图拍的是
哪个角色，以及上面的身份疑问能不能定。

严格按下面的 JSON 结构输出：

{
  "cast": [
    {
      "key": "自己起的短标签，figure_cast 用它指回来",
      "name": "书里给过的名字，没有就留空字符串",
      "look": "一眼认出他的外形，不超过 20 字",
      "best": "这个角色最清楚的一张裁图文件名，挑不出就留空字符串"
    }
  ],
  "figure_cast": [
    {"crop": "裁图文件名，如 p001_f0.jpg", "key": "对应的角色标签"}
  ],
  "resolved": [
    {"page": 3, "issue": "原疑问", "answer": "结论", "evidence": "依据"}
  ],
  "open": [
    {"page": 3, "issue": "原疑问", "reason": "为什么定不了"}
  ]
}

要求：
1. 只输出 JSON，不用代码块，不加解释。四个字段都要出现，没有内容的列表写 []。
2. cast 只收这本书需要做参考图的角色：有台词、推动情节，或者反复出现。只当背景
   的人、人群、路边的行人不要列。
3. key 起一个短标签（A、B、C 或角色名都行），figure_cast 里的 key 必须和它一字
   不差。角色没有名字也照样要列，把 key 当作他的编号。
4. 认人看不换的标记：发饰、发型、图案、毛色、体型。换衣服、换姿势、换角度都不算
   换了人；也不要因为某一页的文字没提到名字，就把他当成新角色。
   裁图边缘可能露出别的角色的一小部分，按画面主体判断：占得最大、最完整的那个人。
   衣服在裁图里看不全时，只看发饰、发型、肤色和脸，不要凭衣服猜。
5. name 只在书里真有名字时才写：文字里出现过，并且能和某张裁图对上。
   不要按"这页文字提到谁就贴给谁"——一页里常有两个角色，文字只提到其中一个。
6. 每张裁图都要在 figure_cast 里出现一次。实在判断不出归属的，key 写空字符串。
7. look 只写画面看得见的，20 字内：先写最认得出的标记（发饰、图案、毛色斑纹），
   再写发型和服装主色。不写性格、身份、关系或动作。
8. best 从你分给他的裁图里挑最合适当参考图的那张：整个人完整（手、脚、头发
   都没被切掉）、脸看得清、旁边没有别人挡着；同样清楚时优先正面的。
   水印和页面文字只在几张差不多时用来分高低，不要因为有水印就一张都不选。
   只能从他自己那组里挑，挑不出就留空字符串。
9. resolved 和 open 逐条处理上面的【待确认的身份疑问】，issue 原样照抄。
   能用裁图和全书文字定的写 resolved，evidence 写依据（第几张裁图、哪一页的文字）；
   定不了的写 open，reason 写原因。不要硬猜。
10. 裁图按质量排过序（正面优先、面积大的优先），顺序和角色主次无关，排第一的不
    一定是主角。
11. 不要给角色编关系、身份或新名字。
"""


def cast_prompt(pages: list[PageContent], picks: list[FigurePick]) -> str:
    """Build the prompt that groups the figure crops into characters."""
    text = TEMPLATE.replace("__COUNT__", str(len(picks)))
    text = text.replace("__PAGES__", _pages_text(pages))
    text = text.replace("__ISSUES__", _issues_text(pages))
    return text.replace("__CROPS__", _crops_text(pages, picks))


# List the story text of every page, so names can be matched to crops.
def _pages_text(pages: list[PageContent]) -> str:
    lines = []
    for page in pages:
        if not page.page_text and not page.figures:
            continue
        text = page.page_text or "（这一页没有故事文字）"
        lines.append(f"{page.filename}：{text}")
    return "\n".join(lines)


# List the uncertainties that ask who someone is.
def _issues_text(pages: list[PageContent]) -> str:
    lines = []
    for page in pages:
        for issue in page.uncertain:
            if any(word in issue for word in IDENTITY_WORDS):
                lines.append(f"{page.filename}：{issue}")
    return "\n".join(lines) or "（这一本没有身份疑问）"


# List the crops in the order their images are given.
def _crops_text(pages: list[PageContent], picks: list[FigurePick]) -> str:
    lines = []
    for number, pick in enumerate(picks, start=1):
        body = _figure_body(pages, pick)
        lines.append(
            f"第 {number} 张 {pick.file} 来自 {pick.page} 的人物 {pick.figure}"
            f"，{body}"
        )
    return "\n".join(lines)


# Return the body words understand wrote for one crop.
def _figure_body(pages: list[PageContent], pick: FigurePick) -> str:
    for page in pages:
        if page.filename != pick.page:
            continue
        for figure in page.figures:
            if figure.index == pick.figure:
                return figure.body or "（未写外形）"
    return "（未写外形）"
