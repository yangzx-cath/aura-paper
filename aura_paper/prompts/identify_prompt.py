"""Prompt that says who appears in every panel of one page."""

from __future__ import annotations

from ..schema.cast import BookCast

TEMPLATE = """这一页的几格画面里，有的人物只露出了一部分。请说出每一格里出现的
是谁、露出了哪些部位。

【这一页的故事文字】
__TEXT__

【角色】
__CAST__

【图片】
__IMAGES__

请按下面的 JSON 结构输出：

{"panels": [{"panel": 0, "people": [{"cast": "c1", "parts": "全身"}]}]}

要求：
1. 只输出 JSON，不用代码块，不加解释。这一页的每一格都要出现，一格都不许漏；
   某一格没人就写 "people": []。
2. cast 只能写【角色】里给出的 id，不要写名字，不要自己编号。
3. parts 写这一格里这个人露出来的部分，比如 全身 / 半身 / 只有头 / 只有手 /
   衣服和腿 / 只有裤子。看得见的部分都要写上，不要只说"部分"。
4. 按衣着、发型、发饰认人，不要按位置猜：同一件衣服出现在哪一格，它就属于谁。
   同一个人的部位散在几格时，每格各写各的，不要只在其中一格写。
5. 看不见脸也要按衣着认出是谁，不能因为看不到脸就当这一格没人。
6. 画框、照片、海报、卡片、屏幕里的形象算道具，不要写进 people；只写真的站
   在这个场景里、会动的角色。框里画的是谁都不用管，也不要拿它去对照参考图。
7. 拿不准是谁的部位不要硬写，宁可留空。
"""


def identify_prompt(
    text: str,
    cast_book: BookCast,
    panels: list[int],
    refs: dict[str, int],
) -> str:
    """Build the prompt that names the people of one page's panels."""
    prompt = TEMPLATE.replace("__TEXT__", text or "（这一页没有故事文字）")
    prompt = prompt.replace("__CAST__", _cast_text(cast_book, refs))
    return prompt.replace("__IMAGES__", _images_text(cast_book, panels, refs))


# List the characters, and which image shows each of them whole.
def _cast_text(cast_book: BookCast, refs: dict[str, int]) -> str:
    lines = []
    for member in cast_book.cast:
        number = refs.get(member.id)
        picture = f"参考图：第{number}张" if number else "（没有参考图）"
        name = member.name or "（无名）"
        lines.append(f"{member.id} {name}｜{member.look}｜{picture}")
    return "\n".join(lines) or "（这本书没有角色）"


# List the images in the order they are given: panels first, then references.
def _images_text(
    cast_book: BookCast,
    panels: list[int],
    refs: dict[str, int],
) -> str:
    names = {member.id: member.name or member.id for member in cast_book.cast}
    lines = []
    for number, index in enumerate(panels, start=1):
        lines.append(f"图{number}：第 {index} 格分镜")
    for cast_id, number in refs.items():
        lines.append(
            f"图{number}：角色 {names.get(cast_id, cast_id)} 的参考图"
        )
    return "\n".join(lines)
