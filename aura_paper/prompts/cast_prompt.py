"""Prompt that groups the figure crops into characters."""

from __future__ import annotations

from ..schema.cast import FigurePick
from ..schema.content import PageContent
from ..schema.voice import CHINESE_CHOICES, CHOICES_BY_LANGUAGE

# Words that mark an uncertainty as being about who someone is.
IDENTITY_WORDS = ("同一人", "身份", "是谁", "指谁", "名字", "对应")

TEMPLATE = """你是一名儿童绘本的角色设定助手。

下面是这本书的逐页文字和 __COUNT__ 张人物裁图。

【逐页文字】
__PAGES__

【待确认的身份疑问】
__ISSUES__

【可选音色】
__VOICES__

【人物裁图】
__CROPS__

请判断这本书需要哪些角色、每张裁图拍的是哪个角色、每个角色用什么声音，并回答
上面的身份疑问。

严格按下面的 JSON 结构输出：

{
  "cast": [
    {
      "key": "短标签，figure_cast 用它指回来",
      "name": "书里给过的名字，没有就留空字符串",
      "look": "一眼认出他的外形，不超过 20 字",
      "voice": "从【可选音色】里原样抄一个 id；不出声的角色留空字符串",
      "best": "最合适当参考图的一张裁图文件名，挑不出就留空字符串"
    }
  ],
  "figure_cast": [
    {"file": "裁图文件名，如 p001_f0.jpg", "key": "对应的角色标签"}
  ],
  "resolved": [
    {"page": 3, "issue": "原疑问", "answer": "结论", "evidence": "依据"}
  ],
  "open": [
    {"page": 3, "issue": "原疑问", "reason": "为什么定不了"}
  ]
}

要求：
1. 只输出 JSON，不用代码块，不加解释。四个字段都要出现，没有内容的写 []。

【cast】
2. 只收需要做参考图的角色：有台词、推动情节，或者反复出现。背景人群、路过的
   行人不列；没有名字的角色照样要列，用 key 当编号。
3. key 起一个短标签（A、B、C 或名字都行），figure_cast 里的 key 必须和它一字
   不差。
4. 判断是不是同一个人，先看这本书里哪类特征没变：有的绘本换衣服不换发型，有的
   换发型不换衣服。按没变的那一类认，另一类只当参考，不当硬指标。
   姿势、角度、远近变了不算换了人；某页没有提到名字也不等于新角色。
   某一类看不全时用其余几类判断，不要凭空猜。
5. name 只在书里真有名字时才写：文字里出现过，又能和某张裁图对上。不要按
   "这页提到谁就贴给谁"来分配，一页里常有两三个人，文字只提到其中一个。
   不要自己编名字。
6. look 只写看得见的外形，20 字内：先写最认得出的标记（发饰、图案、毛色斑纹），
   再写发型和服装主色。不写性格、身份、关系或动作。
7. best 在自己这组裁图里挑最合适当参考图的一张，按顺序比：完整（手、脚、头发
   没被切掉）→ 干净（水印和印刷文字不压在身上）→ 朝向（正面优先，其次斜侧）
   → 前方没有别的角色挡住。挑不出就留空字符串。

【figure_cast】
8. 每张裁图都要出现一次，file 写裁图文件名，key 写它属于哪个角色；判断不出归属
   的 key 写空字符串。裁图边缘可能露出别的角色的一小部分，按占得最大、最完整的
   那个人归属。裁图顺序只是质量排序，排第一的不一定是主角。

【resolved / open】
9. 逐条处理【待确认的身份疑问】，issue 原样照抄。能用裁图和全书文字定的写
   resolved，evidence 写依据（第几张裁图、哪一页的文字）；定不了的写 open，
   reason 写原因。不要硬猜。

【voice】
10. voice 只给会说话的角色：人，以及书里真的开口说过话的动物。不出声的动物
   （只叫、只被人叫名字、只跟着走）留空字符串。
11. voice 从【可选音色】里原样抄一个 id，不要写 id 以外的任何字。按角色的性别和
   年龄挑：成年男人挑成年男声，小孩挑更轻更亮的音色，不要把低沉音色给小孩。
12. 同一本书里性别和年龄都一样的角色，不能共用同一个 id；不够分时先给主角挑最
   贴的，其余角色挑剩下的。
"""


def cast_prompt(
    pages: list[PageContent],
    picks: list[FigurePick],
    *,
    language: str = "zh",
) -> str:
    """Build the prompt that groups the figure crops into characters."""
    choices = CHOICES_BY_LANGUAGE.get(language, CHINESE_CHOICES)
    text = TEMPLATE.replace("__COUNT__", str(len(picks)))
    text = text.replace("__PAGES__", _pages_text(pages))
    text = text.replace("__ISSUES__", _issues_text(pages))
    text = text.replace("__VOICES__", _voices_text(choices))
    return text.replace("__CROPS__", _crops_text(pages, picks))


# List the voices a character may be given, with what each one sounds like.
def _voices_text(choices: tuple[tuple[str, str], ...]) -> str:
    return "\n".join(f"{voice}：{sound}" for voice, sound in choices)


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
        look = _figure_look(pages, pick)
        lines.append(
            f"第 {number} 张 {pick.file} 来自 {pick.page} 的人物 {pick.figure}"
            f"，{look}"
        )
    return "\n".join(lines)


# Return the appearance words understand wrote for one crop.
def _figure_look(pages: list[PageContent], pick: FigurePick) -> str:
    for page in pages:
        if page.filename != pick.page:
            continue
        for figure in page.figures:
            if figure.index != pick.figure:
                continue
            parts = [part for part in (figure.body, figure.outfit) if part]
            return "；".join(parts) or "（未写外形）"
    return "（未写外形）"
