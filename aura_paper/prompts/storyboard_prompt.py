"""Prompt that turns the panels into scenes and shots."""

from __future__ import annotations

from ..schema.cast import BookCast
from ..schema.content import PageContent
from ..schema.identify import BookPeople
from ..schema.location import BookLocations

TEMPLATE = """你是一名儿童绘本动画的分镜导演。

下面是这本书的画风、角色、场地，以及每一块画面的文字。图片按顺序附上：
前 __PANELS__ 张是画面裁图，之后 __REFS__ 张是角色参考图，编号与文字里的
「图 K」一致。

【画风】
__STYLE__

【角色】
__CAST__

【场地】
__PLACES__

【每一格出现的人】
__PEOPLE__

【逐页画面】
__PAGES__

请把这本书拆成场和镜头，给每个镜头配好声音。按下面的 JSON 结构输出：

{
  "scenes": [
    {
      "key": "短标签，shots 用它指回来",
      "name": "这一场在做什么，不超过 8 个字",
      "location": "场地 id，如 l1",
      "pages": ["p001.jpg"]
    }
  ],
  "shots": [
    {
      "scene": "场的短标签",
      "panels": [
        {"page": "p002.jpg", "panel": 0},
        {"page": "p002.jpg", "panel": 1}
      ],
      "cast": ["c1"],
      "join": "硬切",
      "camera": "中景",
      "beats": ["这一镜里发生的动作，一块画面一条"],
      "audio": [
        {"kind": "旁白", "text": "原文照抄", "cast": ""}
      ],
      "continuity": "怎么接上前后镜，一句话"
    }
  ]
}

要求：
1. 只输出 JSON，不用代码块，不加解释。两个字段都要出现，没有内容的写 []。
2. 场按地点和时间划分：地点换了、或者时间跳了，就换场。同一场可以跨好几页，一页里的
   画面也可能分属两场。location 只能填上面给出的场地 id。
3. 镜头是叙事单位，按阅读顺序排。先把同一场里紧密相连的动作和内容合成一镜，一条
   动作链就是一镜，beats 一块画面写一条。一镜不跨场。跨页的一镜，这几页的画面要
   整页列全（同一页里属于别的场的块不算），不要一页只挑几块、另一页又只挑几块。
4. 合并完再看数量：一镜最多 4 块画面。每块画面生成时都是一张图，加上角色图和场地
   图，一次最多送 9 张；超过 4 块就按动作拆成几镜，优先在页边界切——页边界更可能
   是叙事的边界。一页自己就超过 4 块的，这页单独成一镜。
5. 判断紧密相连看叙事，不看画面块数。常见的迹象：一页里的几块小画面信息量小，常常
   是同一个动作的连续步骤；标了「白底」的块没画背景，多半是接着同一处的上一块在演，
   动作也连着。这些只是常见迹象，不是硬规则。标了「完整」的块自己就是一幅有环境的
   画，能单独成镜就单独成镜。
6. cast 只写角色 id，不写名字。这一镜里出现的人都要写上，包括只露半身、被挡
   住的；一镜里看不到人就写 []。【每一格出现的人】已经写明的格子按它写，不要
   自己改。
7. audio 的 kind 只有三种：旁白、对白、音效。
   text 必须从这块画面的文字里逐字照抄，不改写、不合并、不补字、不省略。
   对白和旁白要写 cast，音效的 cast 留空。
   音效只写画面里确实发出的声音，比如"吱呀——"；不写音乐、气氛和心情。
   画面上的每一句文字都要分到某个镜头里，一句都不许漏。
8. join 只有两种：同一场的下一镜写"硬切"，换场的第一镜写"叠化"。
9. camera 从「全景、中景、近景、特写」里挑一个，相邻镜头别连着用同一个景别。
10. 不写秒数、时长和帧数，这些由后面的配音决定。
11. continuity 写这一镜怎么接上前后镜，一句话，不要复述剧情。
"""


def storyboard_prompt(
    pages: list[PageContent],
    cast_book: BookCast,
    places: BookLocations,
    panel_images: list[tuple[str, int, str]],
    ref_images: list[tuple[str, str]],
    people: BookPeople | None = None,
) -> str:
    """Build the prompt that plans the scenes and shots of one book."""
    numbers = {
        (page, index): number
        for number, (page, index, _) in enumerate(panel_images, start=1)
    }
    refs = {
        cast_id: len(panel_images) + number
        for number, (cast_id, _) in enumerate(ref_images, start=1)
    }
    text = TEMPLATE.replace("__PANELS__", str(len(panel_images)))
    text = text.replace("__REFS__", str(len(ref_images)))
    text = text.replace("__STYLE__", places.style or "（未写画风）")
    text = text.replace("__CAST__", _cast_text(cast_book, refs))
    text = text.replace("__PLACES__", _places_text(places))
    text = text.replace("__PEOPLE__", _people_text(people))
    return text.replace("__PAGES__", _pages_text(pages, places, numbers))


# List the panels whose people were named one by one.
def _people_text(people: BookPeople | None) -> str:
    if people is None or not people.panels:
        return "（这一本没有单独认过的格子）"
    lines = []
    for panel in people.panels:
        named = "；".join(
            f"{person.cast} {person.parts}" for person in panel.people
        )
        lines.append(f"{panel.page} 第{panel.panel}格：{named or '没人'}")
    return "\n".join(lines)


# List every character with the image that shows it whole.
def _cast_text(cast_book: BookCast, refs: dict[str, int]) -> str:
    lines = []
    for member in cast_book.cast:
        number = refs.get(member.id)
        picture = f"参考图：第{number}张" if number else "（没有参考图）"
        name = member.name or "（无名）"
        lines.append(f"{member.id} {name}｜{member.look}｜{picture}")
    return "\n".join(lines) or "（这本书没有角色）"


# List every place with the crop that shows its background.
def _places_text(places: BookLocations) -> str:
    lines = []
    for item in places.locations:
        master = item.master or "（无背景图）"
        lines.append(f"{item.id} {item.name}｜{item.light}｜背景图 {master}")
    return "\n".join(lines) or "（这本书没有场地）"


# List every panel with its image number, its text and what it draws.
def _pages_text(
    pages: list[PageContent],
    places: BookLocations,
    numbers: dict[tuple[str, int], int],
) -> str:
    owners = {
        (item.page, item.panel): item.location
        for item in places.panel_locations
    }
    names = {item.id: item.name for item in places.locations}

    lines = []
    for page in pages:
        if not page.panels:
            continue
        lines.append(f"{page.filename}（{page.light or '光照未写'}）")
        for panel in page.panels:
            kind = "白底" if panel.needs_scene else "完整"
            number = numbers.get((page.filename, panel.index), 0)
            place = names.get(owners.get((page.filename, panel.index), ""), "")
            head = f"  第 {panel.index} 块 [{kind}] 图 {number}"
            if place:
                head += f"｜{place}"
            lines.append(head)
            lines.append(f"    文字：{panel.text or '（无文字）'}")
            lines.append(f"    画面：{panel.description or '（未写画面）'}")
    return "\n".join(lines)
