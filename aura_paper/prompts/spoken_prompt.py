"""Prompt that makes the narration read aloud well."""

from __future__ import annotations

from ..schema.shot import Shot

TEMPLATE = """你是一名儿童绘本的朗读编剧。

下面是这本书每一镜的旁白。它们是印在纸上的书面语，直接读出来有些拗口。
请改成适合朗读的说法，意思一点都不能变，只是更顺口。

【旁白】
__LINES__

按下面的 JSON 结构输出：

{
  "lines": [
    {"shot": "j1", "index": 0, "spoken": "改好的说法"}
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
"""


def spoken_prompt(shots: list[Shot]) -> str:
    """Build the prompt that rewrites the narration for reading aloud."""
    return TEMPLATE.replace("__LINES__", _lines_text(shots))


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
