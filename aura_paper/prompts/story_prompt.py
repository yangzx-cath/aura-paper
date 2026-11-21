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
  "identified": [
    {"page": 16, "figure": 1, "name": "角色名", "evidence": "判断依据"}
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
1. 只输出 JSON，不要解释文字，不要使用代码块，九个字段都要出现；
   resolved 和 unresolved 没有内容时写空数组。
2. 所有内容使用中文，角色名除外。
3. characters 用书中最正式的称呼，例如"小鸡球球"而不是"小鸡"或"球球"。
4. characters 只列书里真实出现、有文字依据的角色。书名、电影名、海报/招牌上的
   字、作者、译者、出版社，以及海报/电影里的人物都不是角色。
5. cast 和 characters 是同一批角色，名字一字不差，顺序也一致。look 只写画面里
   看得见的特征：体型、颜色、头发、服装、随身物品；不写性格、身份、关系或动作。
6. 角色的身份要有文字依据：书里写到某个称呼的那几页，画面里对应的人物才是他。
   文字没提到的画面人物，不写进 characters 和 cast，也不要给他起新名字或猜关系；
   他们留在画面描述里。字里没写名字的人物，交给 identified 处理（见规则 8）。
7. references 给每个角色挑一张参考图，用来让后续分镜保持长相一致：挑最容易认出
   这个角色的那一页，全身优先于半身，正面、斜侧优先于侧面、背面，无遮挡优先于
   遮挡，占画面大的优先。name 必须是 characters 里的名字。page 填该页上方「索引：」
   后面的数字，figure 填人物行开头方括号里的数字，不要自己重新编号。why 写理由，
   不超过 15 字。每个角色只挑一张。全书都看不清的角色不要列，也不要拿别的角色的
   图顶替。
8. identified 补认画面上没写名字的人物：逐页看人物列表里 name 为空的那几个，
   通读全书后能确定是谁的，就写出来。
   page 抄那一页上方「索引：」后面的数字，figure 抄人物行开头方括号里的数字，
   不要自己重新编号：该页写「索引：16」、该行是「- [1] （未命名）…」，就写
   {"page": 16, "figure": 1}。
   name 写角色名，evidence 写对得上的具体特征（发色、发饰、服装图案、体型）。
   只有"看起来像"、说不出具体特征的，不要写，留空比猜错好。
9. 叙述者从头到尾没有名字时，不要编名字，用"我"占位；"我"同样要写外形，按画面里
   反复出现的那个孩子来写。
10. summary 概括全书主线，不添加原文没有的情节。
11. setting 和 style 要能代表全书，用于统一后续的画面生成。
12. 处理每页的 uncertain：
    - 通读全书后能从文字、画面描述、前后页关系或角色外形确定的，放入 resolved。
      issue 尽量原样引用该页 uncertain 项；answer 写结论；evidence 写依据，
      必须包含索引或具体文字、画面、外形。
    - 仍然无法确定的，放入 unresolved；issue 原样引用，reason 写清为什么无法确定。
    - index 使用页面的“索引”字段（全局 index，封面为 0），不是故事页序号。
    - 不确定的内容不要硬猜；resolved 只用于解释 uncertain，不要因此往 characters
      或 cast 里新增没有文字依据的角色。
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
