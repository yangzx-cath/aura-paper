"""
Prompt templates for model calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .story import Story
    from .understand import BookContent, PageContent

_LAYOUT_NOTES = {
    "portrait": "这是一张竖幅画面。",
    "landscape": (
        "这是一张横幅画面。先看是一整幅图还是左右两页拼在一起；"
        "如果是两页，按从左到右的顺序阅读和描述。"
    ),
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
  "description": "必填，2-4 句话描述画面：地点、可见人物/物体、动作、氛围，不要复述页面文字",
  "mood": "本页情绪，从词表中选一个：__MOODS__",
  "mood_detail": "词表不贴切时的补充说明，不超过 12 个字，贴切时留空字符串"
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块，六个字段都要出现，description 不能为空。
2. 除 page_text 和 footer 外，其余内容使用中文；这两个字段保留原文语言。
3. page_text 只放讲给孩子听的故事文字：角色对白、拟声词、叙述句。没有就留空字符串。
   海报标题、招牌、标签、价签等画面道具文字，放 footer。
   无字页、局部画面或大面积留白的页面，也要在 description 写清可见内容。
4. footer 放所有不属于故事的印刷文字，没有就留空字符串：
   书名、副标题、作者、译者、出版社、ISBN、定价、条形码、页码、水印，
   以及阅读指导、亲子共读提示、提问、导读等写给大人的内容。
5. page_text 和 footer 都必须逐字转录画面上印刷的文字，保留原有标点与换行，
   用 \\n 表示换行，不要改写，也不要合并两处文字。
6. 无字页很常见。没有故事文字时 page_text 必须是空字符串；不要把画面内容改写成
   page_text，例如不能把"小鸡在走路"写成"小鸡走着走着"。
7. mood 必须严格从词表中选一个。贴切时 mood_detail 留空；都不贴切时选最接近的一个，
   并把真实感受写进 mood_detail。
8. 画面中看不到的信息不要编造。只出现手、脚、背影等局部时，不要判断是谁，也不要
   写角色名或"我"；写清可见的部位、肤色、衣袖、饰品、动作、物品和位置，留给后续
   结合上下文判断。局部有机器结构、明显服装等特征时照实写出来，但不要替它命名。
9. role 只用来标记"不属于故事内容"的页面。判断依据是这一页有没有推进故事情节，
   而不是画面里有没有角色——封面和封底常常也画着主角，但那只是装饰和呼应：
   - cover：封面或书名页，书名、作者、出版社等书目文字是主要内容，画面即使有角色也不构成情节；
   - end：封底，以版权信息或装饰画面为主，画面即使重复了书中的角色，也不推进故事；
   - story：其余所有页。最后一页即使印着版权信息，只要画的是一个新情节，仍然算 story。
   很多绘本没有独立封面和封底，这时每一页都是 story。拿不准时 role 用 story，
   不要因为留白或水印就判成 cover 或 end。
10. __LAYOUT__
"""


def page_prompt(kind: str = "portrait") -> str:
    """Build the prompt for one page, aware of the page shape."""
    note = _LAYOUT_NOTES.get(kind, _LAYOUT_NOTES["portrait"])
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
4. characters 只列书里真实出现、有文字依据的角色。书名、电影名、海报/招牌上的
   字、作者、译者、出版社，以及海报/电影里的人物都不是角色。
5. cast 和 characters 是同一批角色，名字一字不差，顺序也一致。look 只写画面里
   看得见的特征：体型、颜色、头发、服装、随身物品；不写性格、身份、关系或动作。
6. 角色的身份要有文字依据：书里写到某个称呼的那几页，画面里对应的人物才是他。
   文字没提到的画面人物，不写进 characters 和 cast，也不要给他起名字或猜关系；
   他们留在画面描述里。只有手、脚、背影等局部时，不要当成新角色，也不要猜是谁。
7. 叙述者从头到尾没有名字时，不要编名字，用"我"占位；"我"同样要写外形，按画面里
   反复出现的那个孩子来写。
8. summary 概括全书主线，不添加原文没有的情节。
9. setting 和 style 要能代表全书，用于统一后续的画面生成。
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


_SCREENPLAY_TEMPLATE = """你是一名儿童绘本编剧。请根据全书设定和本页内容，写出这一页的分镜提示和朗读台词。

全书设定：
- 语言：__LANGUAGE__
- 角色：__CHARACTERS__
- 外形：__CAST__
- 地点：__SETTING__
- 画风：__STYLE__
- 全书主线：__SUMMARY__

上一页内容（不要重复）：
__PREVIOUS__

本页内容：
- 页码：第 __INDEX__ 页
- 文字：__PAGE_TEXT__
- 画面：__DESCRIPTION__
- 情绪：__MOOD__

只输出 JSON，不要解释，不要用代码块；两个字段都要有：
{
  "beat": "这一页看得见的新变化，20-30 字",
  "lines": [
    {"kind": "narration", "speaker": "", "text": "旁白"},
    {"kind": "dialogue", "speaker": "角色名", "text": "对白"}
  ]
}

规则：
1. beat 用中文，写“谁做了什么、结果或情绪怎么变”，20-30 字。不要写镜头运动、
   转场，也不要写“铺垫、承接、形成结尾”等编辑语；写动作和变化，不要只复述画面。
   画面没有明显动作时，写角色最明显的动作或反应，不编新情节。
2. lines 用__LANGUAGE__，按播放顺序排列。每条要完整自然、能单独听懂；可把一句
   原文拆成几条短句，但不要把两句合并。用 4-12 岁孩子听得懂的话，避免长从句、
   插入语和连续重复的句式。
3. kind 只用 narration 或 dialogue。只有“文字”中引号里的原话才是 dialogue；
   引号外的第一人称、心理活动和普通叙述都是 narration，speaker 留空。
4. dialogue 必须照抄引号里的原话，去掉引号和“他说、她问、I say、he says, smiling”
   等说明文字；说明文字需要时另写 narration。
   例：原文 “Kuan can buy it,” he says, smiling. → dialogue 为 Kuan can buy it，
   speaker 为 Dad。
5. narration 用来读“文字”里的叙述句，或连接页面、交代画面里看得见的动作；
   无字页可返回空 lines。不编原文没有的情节、关系、身份或姓名；画面里未被文字
   提到的人，只写动作，不给称呼。
6. 局部画面例外：画面只描述手、脚、背影时，结合全书角色、外形和上一页内容判断
   是谁；能判断就用角色名或“我”，不能判断就只写动作，不硬猜。
7. speaker 只用全书角色或“我”；说话人不在角色表里时不要猜名字，把原话写成
   narration。叙述者是“我”时，旁白用 I，不要写 the child、the boy、the girl。
8. 不要重复上一页的 beat 或台词，角色称呼前后一致。
9. 输出前自检：beat 无镜头/编辑语；dialogue 只来自引号；引号外第一人称都是
   narration；每条 line 自然完整。
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

请把这一页绘本画面制作成一段连贯的动画。提供的原图只作为参考，不作为视频起始帧。

故事背景：
- 角色：__CHARACTERS__
- 地点：__SETTING__
- 画风：__STYLE__
- 全书主线：__SUMMARY__

本页分镜：
- 页码：第 __INDEX__ 页
- 剧情：__BEAT__
- 画面：__DESCRIPTION__
- 情绪：__MOOD__

要求：
1. 原图只用于参考角色造型、画风、配色和构图；只表现本页画面内容，不新增角色，
   不改变角色造型、服装和画面风格。
2. 画面中不要出现文字、字幕、水印或边框。
3. 动作自然、幅度适中，适合儿童观看，避免剧烈晃动、快速变焦和恐怖画面。
4. 镜头运动克制，不切换场景；竖幅使用 [Push in] 缓慢推进，横幅从左到右缓慢平移。
5. 剧情提示只表现本页画面里的动作；不添加原文没有的情节，不描述画面外的内容。
6. __LAYOUT__
"""

_SHOT_LAYOUT_NOTES = {
    "portrait": "这是一张竖幅画面，镜头保持稳定。",
    "landscape": "这是一张横幅画面，镜头从左到右缓慢平移。",
}


def shot_prompt(
    page: PageContent,
    story: Story,
    *,
    beat: str = "",
) -> str:
    """Build the video prompt for one page."""
    characters = "、".join(story.characters) or "（未提供）"
    layout = _SHOT_LAYOUT_NOTES.get(page.kind, _SHOT_LAYOUT_NOTES["portrait"])

    prompt = _SHOT_TEMPLATE.replace("__CHARACTERS__", characters)
    prompt = prompt.replace("__SETTING__", story.setting or "（未提供）")
    prompt = prompt.replace("__STYLE__", story.style or "（未提供）")
    prompt = prompt.replace("__SUMMARY__", story.summary or "（未提供）")
    prompt = prompt.replace("__INDEX__", str(page.index + 1))
    prompt = prompt.replace("__BEAT__", beat.strip() or "（按画面自然动作）")
    prompt = prompt.replace(
        "__DESCRIPTION__", page.description or "（未提供）"
    )
    prompt = prompt.replace("__MOOD__", page.mood or "（未提供）")
    return prompt.replace("__LAYOUT__", layout)
