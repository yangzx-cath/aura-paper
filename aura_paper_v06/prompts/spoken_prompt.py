"""Prompt that makes the narration read aloud well and checks the sounds."""

from __future__ import annotations

from ..schema.content import PageContent
from ..schema.shot import Shot

TEMPLATE = """你是一名儿童绘本的朗读编剧。

下面是这本书每一镜的旁白。它们是印在纸上的书面语，直接读出来有些拗口。
请改成适合朗读的说法，意思一点都不能变，只是更顺口。

【旁白】
__LINES__

【音效】
__SOUNDS__

按下面的 JSON 结构输出：

{
  "lines": [
    {"shot": "j1", "index": 0, "spoken": "改好的说法"}
  ],
  "sounds": [
    {"shot": "j14", "index": 2, "keep": false}
  ]
}

要求：
1. 只输出 JSON，不用代码块，不加解释。
2. 一段对一段：shot 和 index 原样照抄，不合并、不拆分、不漏条。
3. 只改措辞。不加情节、不删情节、不换顺序、不改人物关系。
4. 人名、拟声词（滴答滴答、阿嚏、吱呀）和数字必须原样保留，
   "三块"不能变成"两块"，"九块"不能变成"很多块"。
5. 保持讲述的语气，不要变成角色说话的口吻，也不要加"呀""哦""啦"这类语气词。
6. 长度和原来差不多，允许的变化不超过三成。
7. 去掉排版用的引号，其余标点照原样。

【音效复核】
8. 音效是从画面上抄下来的拟声词，可能是读音错的、也算不准是哪个东西发出的。
   逐条对照这一镜的画面和动作：场上有没有东西能发出这个声音。
9. 说不通就 keep 写 false，例如小狗叼着卡片跑开、场上并没有门，就不该有"吱呀"。
   说得通就写 true；拿不准但场上有可能是它的，也写 true，不要多删。
10. 不要改成你觉得对的词，只决定留还是删。
"""


def spoken_prompt(
    shots: list[Shot],
    pages: list[PageContent] | None = None,
) -> str:
    """Build the prompt that rewrites the narration and checks the sounds."""
    prompt = TEMPLATE.replace("__LINES__", _lines_text(shots))
    return prompt.replace("__SOUNDS__", _sounds_text(shots, pages or []))


# List the sound effects with the picture and the action they belong to.
def _sounds_text(shots: list[Shot], pages: list[PageContent]) -> str:
    looks = {
        (page.filename, panel.index): panel.description
        for page in pages
        for panel in page.panels
    }
    lines = []
    for shot in shots:
        seen = "；".join(
            looks.get((panel.page, panel.panel), "") for panel in shot.panels
        )
        beats = " ".join(shot.beats)
        for number, line in enumerate(shot.audio):
            if line.kind != "音效":
                continue
            lines.append(
                f"{shot.id}｜{number}｜{line.text}｜画面：{seen or '（没写）'}"
                f"｜动作：{beats or '（没写）'}"
            )
    return "\n".join(lines) or "（这本书没有音效）"


# List every narration line with the shot it belongs to.
def _lines_text(shots: list[Shot]) -> str:
    lines = []
    for shot in shots:
        for number, line in enumerate(shot.audio):
            if line.kind != "旁白":
                continue
            camera = shot.camera or "未写景别"
            lines.append(f"{shot.id}｜{number}｜{camera}｜{line.text}")
    return "\n".join(lines) or "（这本书没有旁白）"
