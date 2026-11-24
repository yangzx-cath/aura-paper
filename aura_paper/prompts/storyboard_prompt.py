"""Prompt that turns the panels into scenes and shots."""

from __future__ import annotations

from ..schema.cast import BookCast
from ..schema.content import PageContent, language_of
from ..schema.identify import BookPeople
from ..schema.location import BookLocations

TEMPLATE = """你是一名儿童绘本动画的分镜导演。

下面是这本书的画风、角色、场地，以及每一格画面的文字。图片按顺序附上：
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
      "beats": ["这一镜里发生的动作，一格画面一条"],
      "audio": [
        {"kind": "旁白", "text": "原文照抄", "cast": ""}
      ],
      "continuity": "怎么接上前后镜，一句话"
    }
  ]
}

要求：
1. 只输出 JSON，不用代码块，不加解释。两个字段都要出现，没有内容的写 []。
   panels 里的 panel 填那个格前面写的数字，它从 0 起。
2. 场按地点和时间划分：地点换了、或者时间跳了，就换场。同一场可以跨好几页，一页里的
   画面也可能分属两场。location 只能填上面给出的场地 id。
3. 镜头是叙事单位，按阅读顺序排。先把同一场里紧密相连的动作和内容合成一镜，一条
   动作链就是一镜。一镜不跨场。跨页的一镜，这几页的画面要整页列全（同一页里属于
   别的场的格不算），不要一页只挑几格、另一页又只挑几格。
   beats 一格画面写一条，只写画面上确实看得见的动作。动作归谁按画面判断：看谁的
   手在施力、谁的身体前倾、谁在后退，再结合表情——皱眉使劲、表情得意的是主动的
   一方，吃痛、惊讶、闭眼、往后仰的是被动的一方。判断不出是谁做的，就写"两人
   拉扯在一起"这种不点名的说法，不要按台词猜。
   不写打、踢、咬、抓、摔这些攻击动作：两人有身体接触时，只写"伸手去推""拉住
   对方的手""护住积木"，冲突靠表情、距离和姿态表现。
4. 一镜装多少格，先看页边界：一镜不拆页，一页的格要么全在这一镜，要么整页归别的
   镜。在此之上有两个上限：一镜最多 4 格画面——每格画面生成时都是一张图，加上
   角色图和背景图，一次最多送 9 张；一镜的声音加起来不超过 13 秒，中文大约 50
   字，英文大约 30 个词。哪个先到就按哪个拆，拆都在页边界拆成几镜，页边界更可能
   是叙事边界。一页自己就超过上限时，这一页单独成一镜。
5. 判断紧密相连看叙事，不看画面分了几格。常见的迹象：一页里的几格小画面信息量小，
   常常是同一个动作的连续步骤；标了「白底」的格没画背景，多半是接着同一处的
   上一格在演，动作也连着。这些只是常见迹象，不是硬规则。标了「完整」的格自己
   就是一幅有环境的画，能单独成镜就单独成镜。
6. cast 只写角色 id，不写名字。这一镜里出现的人都要写上，包括只露半身、被挡
   住的；一镜里看不到人就写 []。【每一格出现的人】已经写明的格按它写，不要
   自己改。
7. audio 的 kind 只有三种：旁白、对白、音效；音效只写画面里确实发出的声音，
   不写音乐、气氛和心情。
   画面上的文字要逐字照抄：不改写、不合并、不补字、不省略，每一句都要分到某个
   镜头里，一句都不许漏。
   对白写说话人的 cast，旁白和音效的 cast 留空。分不清是谁说的就留空，不要猜。
8. 一镜的画面全都没有文字时，要补一句声音过渡，两种做法挑更顺的一种：
   一是照这一镜发生的事写一句旁白，事情从 beats 里取，不复述画面上的姿势；
   二是后一镜有好几句声音时，把其中最贴这一镜的一句（旁白或对白）挪过来，
   挪走后后一镜不再念它；这一句不算漏，只是换了镜头来念。后一镜只剩一句时不挪。
   补的话要像讲给孩子听：短句、具体、口语，一句说一件事；不用"做手工""玩"这类
   笼统的词带过，也不写画面里看不出的心情和道理。
   旁白和补的话都用画面文字同一种语言写（这本书是__LANG__），不要翻成中文。
   相邻两镜不念同一句。
9. join 只有两种：同一场的下一镜写"硬切"，换场的第一镜写"叠化"；第一镜写
   "硬切"，它前面没有镜头可接。
10. camera 从「全景、中景、近景、特写」里挑一个，相邻镜头别连着用同一个景别。
11. 输出里不写秒数、时长和帧数，这些由后面的配音决定；你只保证每镜的声音不超过
    13 秒。
12. continuity 写这一镜怎么接上前后镜，一句话，不要复述剧情。
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
    text = text.replace(
        "__LANG__", _language_name(_book_language(pages, cast_book))
    )
    return text.replace("__PAGES__", _pages_text(pages, places, numbers))


# Read the language of the book, from the cast or from its own words.
def _book_language(pages: list[PageContent], cast_book: BookCast) -> str:
    if cast_book.language:
        return cast_book.language
    return language_of("".join(page.page_text for page in pages))


# Name the language a book is written in, for the prompt.
def _language_name(language: str) -> str:
    return "英语" if language == "en" else "中文"


# List the panels whose people were named one by one.
def _people_text(people: BookPeople | None) -> str:
    if people is None or not people.panels:
        return "（这一本没有单独认过的格）"
    lines = []
    for panel in people.panels:
        named = "；".join(
            f"{person.cast} {person.parts}" for person in panel.people
        )
        lines.append(f"{panel.page} 第 {panel.panel} 格：{named or '没人'}")
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
            head = f"  第 {panel.index} 格 [{kind}] 图 {number}"
            if place:
                head += f"｜{place}"
            lines.append(head)
            lines.append(f"    文字：{panel.text or '（无文字）'}")
            lines.append(f"    画面：{panel.description or '（未写画面）'}")
    return "\n".join(lines)
