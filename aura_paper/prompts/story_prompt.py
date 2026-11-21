"""Prompt that turns the page contents into a story outline."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..understand import BookContent, Figure

TEMPLATE = """你是一名儿童绘本的编剧助手。

下面是一本绘本逐页的内容，共 __COUNT__ 页。

__PAGES__

请通读全书，严格按下面的 JSON 结构输出：

{
  "characters": ["主要角色，用书中出现的称呼"],
  "cast": [
    {"name": "角色名，和 characters 完全一致", "look": "外形，不超过 20 字"}
  ],
  "on_page": [
    {"page": 2, "names": ["角色名"]}
  ],
  "references": [
    {"name": "角色名", "page": 12, "figure": 0, "why": "选择理由"}
  ],
  "setting": "故事发生的地点与环境，不超过 20 字",
  "style": "画面风格关键词，不超过 20 字",
  "summary": "全书主线，100-200 字",
  "resolved": [
    {"index": 18, "issue": "原 uncertain 项", "answer": "结论", "evidence": "依据"}
  ],
  "unresolved": [
    {"index": 26, "issue": "原 uncertain 项", "reason": "无法确定的原因"}
  ]
}

要求：
1. 只输出 JSON，不用代码块，不加解释。九个字段都要出现，没有内容的列表写 []。
2. 除角色名外，全部用中文。
3. characters 只列书里真实出现、有文字依据的角色，用书中的正式称呼，例如"小鸡
   球球"而不是"小鸡"或"球球"。书名、电影名、招牌上的字、作者、译者、出版社，
   以及海报和电影里的人物都不是角色。
4. cast 与 characters 同名同序。look 只写画面看得见的，20 字内：先写最能认出他
   的标记（身上的图案、配饰、发饰、毛色斑纹），再写发型和服装颜色；不写性格、
   身份、关系或动作。
5. 画面里没被文字指认的人物，不进 characters 和 cast，也不要给新名字或猜关系；
   分别是谁交给 on_page 判断。
6. references 给每个角色挑一张最容易认出他的图，用来让后续分镜保持长相一致：
   全身优先于半身，正面、斜侧优先于侧面、背面，无遮挡优先于遮挡，占画面大的优先。
   每角色只挑一张；全书都看不清的不列，也不要拿别的角色顶替。
   name 必须是 characters 里的名字。page 填该页上方「索引：」后面的数字，figure
   填人物行开头方括号里的数字，不要自己重新编号。why 不超过 15 字。
7. on_page 写每页画面上出现了谁，用来定这一页有哪几个角色。一页一条，names 按
   cast 的顺序，只写有把握的，看不出来就写 []。
   人露了一部分也算：只有半个身子、只露一只手、只露出衣服的一角，只要特征对
   得上就写。服装和配色对得上就算认得出，人物缩得小、看不清发型不算反证。
   关系不明不影响出场判断——认得出是谁就写，两人是什么关系交给规则 11。
   只能"看起来像"、说不出具体特征的不要写，漏掉比认错好。
8. 叙述者全书没有名字时不要编，用"我"占位，并按画面里反复出现的那个孩子写外形。
9. summary 概括全书主线，不添加原文没有的情节。
10. setting 和 style 要能代表全书，用于统一后续的画面生成。
11. 处理每页的 uncertain：
    - 能从文字、画面描述、前后页关系或角色外形确定的，放 resolved，issue 尽量
      原样引用该页 uncertain 项，answer 写结论，evidence 写依据（含索引或具体
      文字、画面、外形）。
    - 定不了的放 unresolved，issue 原样引用，reason 写原因。
    - index 用页面的「索引」值（全局，封面为 0），不是故事页序号。
    - 不要硬猜；resolved 只用来解释 uncertain，不要借此往 characters 或 cast
      里加角色。
"""


def story_prompt(content: BookContent) -> str:
    """Build the prompt that turns page contents into a story outline."""
    pages = content.story_pages
    blocks = []
    for number, page in enumerate(pages, start=1):
        block = (
            f"第 {number} 页\n"
            f"索引：{page.index}\n"
            f"文字：{page.page_text or '（无字）'}\n"
            f"画面：{page.description}"
        )
        if page.figures:
            block += "\n人物：\n" + "\n".join(
                _figure_line(figure) for figure in page.figures
            )
        if page.uncertain:
            block += "\nuncertain：" + "；".join(page.uncertain)
        blocks.append(block)

    prompt = TEMPLATE.replace("__PAGES__", "\n\n".join(blocks))
    return prompt.replace("__COUNT__", str(len(pages)))


# Render one figure as a single line of identity evidence.
def _figure_line(figure: Figure) -> str:
    parts = [
        figure.name or "（未命名）",
        figure.view or "-",
        figure.facing or "-",
        f"遮挡{figure.occlusion or '-'}",
        f"占画面 {_area_text(figure.box)}",
        figure.body,
    ]
    if figure.outfit:
        parts.append(figure.outfit)
    return f"    - [{figure.index}] " + "｜".join(
        part for part in parts if part
    )


# Turn a crop box into the share of the page it covers.
def _area_text(box: list[int] | None) -> str:
    if not box:
        return "-"
    left, top, right, bottom = box
    return f"{(right - left) * (bottom - top) / 100:.0f}%"
