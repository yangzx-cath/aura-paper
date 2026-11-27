"""Prompt that groups the panels into places and names the art style."""

from __future__ import annotations

from ..schema.content import PageContent

TEMPLATE = """你是一名儿童绘本的美术与场景设定助手。

下面是这本书每一页的画面说明，以及 __FULL__ 张"完整画面"裁图 —— 这些裁图里
有环境；标记为「白底」的画面只有人物和道具。

【逐页画面】
__PAGES__

【完整画面】
__FULLS__

请判断这本书有哪些场地、每块画面属于哪个场地、每个场地用哪张裁图当背景，
并提炼全书的画风。

严格按下面的 JSON 结构输出：

{
  "style": "全书画风，不超过 60 字",
  "locations": [
    {
      "key": "短标签，panel_locations 用它指回来",
      "name": "场地的短名词，如客厅、门口、草地",
      "light": "这个场地的时间与光照",
      "master": "当背景的裁图文件名，挑不出就留空字符串"
    }
  ],
  "panel_locations": [
    {"page": "p005.jpg", "panel": 0, "key": "对应的场地标签"}
  ]
}

要求：
1. 只输出 JSON，不用代码块，不加解释。三个字段都要出现，没有内容的写 []。

【场地】
2. 先看完所有裁图再分场地。同一个场地只写一次：换个角度、换件事做还是同一处；
   墙、地板、窗、家具明显不同的才分开。
3. 不同孩子的家是两个场地：「花花在家」是花花的家，「小满画好了卡片」是小满的
   家，屋里摆设再像也要分开。文字没说在哪一家的，看画面里是谁、摆着谁的东西。
4. 只写书里真有的场地，不要多编；只出现一次的场地也要写出来。

【每块画面】
5. 每块画面都要在 panel_locations 里出现一次，page 用文件名；没有面板的页不写。
6. 没有环境的画面（标为「白底」，或者标为「完整」但背景是纯白）跟着它前面最近
   的那块有环境的画面走。文字明确说人物换了地方才不跟；前面没有就跟后面最近的；
   两头都判断不出，key 写空字符串。

【master / light / style】
7. master 必须是【完整画面】里的一张裁图文件名：选看得到最多环境、人物没占满
   画面、没被大段文字遮住的那张，背景纯白的不选。每个场地一张，挑不出就留空
   字符串。
8. light 抄这个场地画面本身的 light，不写心情和气氛。
9. style 只写画材、笔触、色彩和光影，不写角色、道具和情节。
"""


def location_prompt(
    pages: list[PageContent],
    full: list[tuple[str, int, str]],
) -> str:
    """Build the prompt that groups panels into places."""
    text = TEMPLATE.replace("__FULL__", str(len(full)))
    text = text.replace("__PAGES__", _pages_text(pages))
    return text.replace("__FULLS__", _fulls_text(pages, full))


# List every panel with the place words understand already saw.
def _pages_text(pages: list[PageContent]) -> str:
    lines = []
    for page in pages:
        if not page.panels:
            continue
        lines.append(f"{page.filename}（{page.light or '光照未写'}）")
        for panel in page.panels:
            kind = "白底" if panel.needs_scene else "完整"
            lines.append(f"  第 {panel.index} 块 [{kind}] {panel.description}")
    return "\n".join(lines)


# List the crops in the order their images are given.
def _fulls_text(
    pages: list[PageContent],
    full: list[tuple[str, int, str]],
) -> str:
    lines = []
    for number, (page_name, index, crop) in enumerate(full, start=1):
        description = _panel_description(pages, page_name, index)
        lines.append(
            f"第 {number} 张 {crop} = {page_name} 第 {index} 块，{description}"
        )
    return "\n".join(lines)


# Return the description understand wrote for one panel.
def _panel_description(
    pages: list[PageContent],
    page_name: str,
    index: int,
) -> str:
    for page in pages:
        if page.filename != page_name:
            continue
        for panel in page.panels:
            if panel.index == index:
                return panel.description or "（未写画面）"
    return "（未写画面）"
