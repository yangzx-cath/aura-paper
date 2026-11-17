"""
Prompt templates for model calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .story import Story
    from .understand import BookContent, PageContent

_LAYOUT_NOTES = {
    "single": "这是一页单页画面。",
    "spread": "这是一张跨页画面，包含左右两页，请按从左到右的顺序阅读和描述画面。",
}

# A closed set keeps mood usable for music and tone mapping.
_MOOD_WORDS = (
    "好奇、欢快、兴奋、惊喜、温暖、平静、期待、担忧、害怕、生气、失落、悲伤"
)

_PAGE_TEMPLATE = """你是一名儿童绘本内容理解助手。

请阅读这一页绘本，严格按下面的 JSON 结构输出：

{
  "role": "本页在书中的角色，从 cover、story、end 中选一个",
  "page_text": "属于故事本身的印刷文字，逐字转录，没有时留空字符串",
  "footer": "不属于故事的印刷文字，逐字转录，没有时留空字符串",
  "description": "用 2-4 句话描述画面：地点、角色、动作、氛围，不要复述页面文字",
  "mood": "本页情绪，从词表中选一个：__MOODS__",
  "mood_detail": "词表不贴切时的补充说明，不超过 12 个字，贴切时留空字符串"
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，六个字段都要出现。
2. 除 page_text 和 footer 外，其余内容使用中文；这两个字段保留原文语言。
3. page_text 只放讲给孩子听的故事文字：角色对白、拟声词、叙述句。没有就留空字符串。
   画面里画出来的文字，例如海报标题、招牌、标签、价签，属于道具不属于故事，放 footer。
4. footer 放所有不属于故事的印刷文字，没有就留空字符串：
   书名、副标题、作者、译者、出版社、ISBN、定价、条形码、页码，
   以及阅读指导、亲子共读提示、提问、导读等写给大人的内容。
5. page_text 和 footer 都必须逐字转录画面上印刷的文字，保留原有标点与换行，用 \\n 表示换行，不要改写，也不要合并两处文字。
6. 无字页很常见。画面没有故事文字时 page_text 必须是空字符串，也不能把画面改写成句子，例如不能把"小鸡在走路"写成"小鸡走着走着"。
7. mood 必须严格从词表中选一个。贴切时 mood_detail 留空字符串，都不贴切时选最接近的一个，并把真实感受写进 mood_detail。
8. 画面中看不到的信息不要编造。
9. role 只用来标记"不属于故事内容"的页面。判断依据是这一页有没有推进故事情节，
   而不是画面里有没有角色——封面和封底常常也画着主角，但那只是装饰和呼应：
   - cover：封面或书名页，书名、作者、出版社等书目文字是主要内容，画面即使有角色也不构成情节；
   - end：封底，以版权信息或装饰画面为主，画面即使重复了书中的角色，也不推进故事；
   - story：其余所有页。最后一页即使印着版权信息，只要画的是一个新情节，仍然算 story。
   很多绘本没有独立封面和封底，这时每一页都是 story。
10. __LAYOUT__
"""


def page_prompt(kind: str = "single") -> str:
    """Build the prompt for one page, aware of single or spread layout."""
    note = _LAYOUT_NOTES.get(kind, _LAYOUT_NOTES["single"])
    prompt = _PAGE_TEMPLATE.replace("__LAYOUT__", note)
    return prompt.replace("__MOODS__", _MOOD_WORDS)


_STORY_TEMPLATE = """你是一名儿童绘本的编剧助手。

下面是一本绘本逐页的内容，共 __COUNT__ 页。

__PAGES__

请通读全书，严格按下面的 JSON 结构输出：

{
  "characters": ["主要角色，用书中出现的称呼"],
  "cast": [
    {"name": "角色名，和 characters 完全一致", "look": "外形，不超过 20 字"}
  ],
  "setting": "故事发生的地点与环境，不超过 20 字",
  "style": "画面风格关键词，不超过 20 字",
  "summary": "全书主线，100-200 字"
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，五个字段都要出现。
2. 所有内容使用中文，角色名除外。
3. characters 用书中最正式的称呼，例如"小鸡球球"而不是"小鸡"或"球球"。
4. characters 只列书里真实出现的角色。书名、电影名、海报和招牌上的字、
   作者、译者、出版社都不是角色。
5. 叙述者从头到尾没有名字时，不要给他编名字，用"我"占位。
6. cast 和 characters 是同一批角色，名字一字不差，顺序也一致。
7. look 只写画面里看得见的特征：体型、颜色、头发、服装、随身物品。
   不写性格、身份和人物关系，也不要写动作。
8. 叙述者"我"同样要写外形，按画面里反复出现的那个孩子来写。
9. 家人算角色；店员、其他观众、路人只是背景，不算。
   海报里和电影里的人物也不算。
10. summary 概括全书主线，不添加原文没有的情节。
11. setting 和 style 要能代表全书，用于统一后续的画面生成。
"""


def story_prompt(content: BookContent) -> str:
    """Build the prompt that turns page contents into a story outline."""
    pages = content.story_pages
    blocks = []
    for page in pages:
        blocks.append(
            f"第 {page.index + 1} 页\n"
            f"文字：{page.page_text or '（无字）'}\n"
            f"画面：{page.description}\n"
            f"情绪：{page.mood}"
        )

    prompt = _STORY_TEMPLATE.replace("__PAGES__", "\n\n".join(blocks))
    return prompt.replace("__COUNT__", str(len(pages)))


_SCREENPLAY_TEMPLATE = """你是一名儿童绘本的编剧助手。

全书设定：
- 语言：__LANGUAGE__
- 角色：__CHARACTERS__
- 外形：__CAST__
- 地点：__SETTING__
- 画风：__STYLE__
- 全书主线：__SUMMARY__

上一页的内容（不要重复）：
__PREVIOUS__

本页内容：
- 页码：第 __INDEX__ 页
- 文字：__PAGE_TEXT__
- 画面：__DESCRIPTION__
- 情绪：__MOOD__

请严格按下面的 JSON 结构输出这一页的内容：

{
  "beat": "这一页推进了什么，20-30 字",
  "lines": [
    {"kind": "narration", "speaker": "", "text": "念出来的旁白"},
    {"kind": "dialogue", "speaker": "角色名", "text": "角色的对白"}
  ]
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，beat 和 lines 都要出现。
2. beat 使用中文；lines 全部使用__LANGUAGE__。
   这一页没有原文时，旁白也要用__LANGUAGE__写，不要出现别的语言。
3. beat 写给分镜看：这一页新发生了什么，不要复述画面，也不要复述旁白。
4. lines 是念给孩子听的话，按播放顺序排列，一条对应一句话。
   旁白用 4-12 岁孩子听得懂的词，一句话只说一件事，不用生僻词和成语。
   英文旁白用常见词和短句，避免长从句和插入语。
5. 对白是书上原有的台词，必须照抄，不要改写，也不要编新台词。
6. 旁白只在需要时出现：把这一页接上，或交代画面里看不出来的事。
   对白已经把这一页讲清楚时，可以完全没有旁白。
   无字页也可以不写旁白，lines 直接返回空数组。
   要写旁白时只写画面里看得见的动作和情景，
   不推测人物关系、身份、姓名，也不替角色编台词。
7. kind 只能是 narration 或 dialogue。
   narration 是旁白，speaker 留空字符串。
   dialogue 是角色说的话，speaker 填角色名。
   第一人称叙述者自己说的话，speaker 填"我"。
8. 不要给没有名字的角色编名字，speaker 只能用全书设定里的称呼或"我"。
9. 接着上一页往下写，不要重复上一页已经念过的内容。
10. 使用全书统一的角色称呼，不添加原文没有的情节。
11. 旁白提到角色时以外形为准，不要给他加原文没说的性别、年龄或亲属关系。
"""


def screenplay_prompt(
    page: PageContent,
    story: Story,
    *,
    previous: str = "",
    language: str = "",
) -> str:
    """Build the prompt that plans one page as a scene."""
    characters = "、".join(story.characters) or "（未提供）"
    prompt = _SCREENPLAY_TEMPLATE.replace("__CHARACTERS__", characters)
    prompt = prompt.replace("__LANGUAGE__", language or "原文的语言")
    prompt = prompt.replace("__CAST__", _cast_text(story))
    prompt = prompt.replace("__SETTING__", story.setting or "（未提供）")
    prompt = prompt.replace("__STYLE__", story.style or "（未提供）")
    prompt = prompt.replace("__SUMMARY__", story.summary or "（未提供）")
    prompt = prompt.replace("__PREVIOUS__", previous or "（这是第一页）")
    prompt = prompt.replace("__INDEX__", str(page.index + 1))
    prompt = prompt.replace("__PAGE_TEXT__", page.page_text or "（无字）")
    prompt = prompt.replace(
        "__DESCRIPTION__", page.description or "（未提供）"
    )
    return prompt.replace("__MOOD__", page.mood or "（未提供）")


# Render the cast as "名字（外形）" so a scene knows how each one looks.
def _cast_text(story: Story) -> str:
    parts = []
    for member in story.cast:
        if member.look:
            parts.append(f"{member.name}（{member.look}）")
        else:
            parts.append(member.name)
    return "；".join(parts) or "（未提供）"


_SHOT_TEMPLATE = """你是一名儿童绘本动画分镜师。

请把这一页绘本画面制作成一段连贯的动画。原图会作为视频首帧，
角色造型、画风、配色和构图必须与原图保持一致。

故事背景：
- 角色：__CHARACTERS__
- 地点：__SETTING__
- 画风：__STYLE__
- 全书主线：__SUMMARY__

本页分镜：
- 页码：第 __INDEX__ 页
- 画面：__DESCRIPTION__
- 情绪：__MOOD__

要求：
1. 只表现本页画面内容，不新增角色，不改变角色外观和服装。
2. 保持原图画风、配色和构图，画面中不要出现文字、字幕、水印或边框。
3. 动作自然、幅度适中，适合儿童观看，避免剧烈晃动、快速变焦和恐怖画面。
4. 镜头缓慢推进，使用 [Push in]，不要切换到其他场景。
5. 不添加原文没有的情节，不描述画面外的内容。
6. __LAYOUT__
"""

_SHOT_LAYOUT_NOTES = {
    "single": "这是一页单页画面，镜头保持稳定。",
    "spread": "这是一张跨页画面，动作从左到右连贯展开。",
}


def shot_prompt(
    page: PageContent,
    story: Story,
) -> str:
    """Build the video prompt for one page."""
    characters = "、".join(story.characters) or "（未提供）"
    layout = _SHOT_LAYOUT_NOTES.get(page.kind, _SHOT_LAYOUT_NOTES["single"])

    prompt = _SHOT_TEMPLATE.replace("__CHARACTERS__", characters)
    prompt = prompt.replace("__SETTING__", story.setting or "（未提供）")
    prompt = prompt.replace("__STYLE__", story.style or "（未提供）")
    prompt = prompt.replace("__SUMMARY__", story.summary or "（未提供）")
    prompt = prompt.replace("__INDEX__", str(page.index + 1))
    prompt = prompt.replace(
        "__DESCRIPTION__", page.description or "（未提供）"
    )
    prompt = prompt.replace("__MOOD__", page.mood or "（未提供）")
    return prompt.replace("__LAYOUT__", layout)
