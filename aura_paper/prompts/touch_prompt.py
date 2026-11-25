"""Prompt that names the thing a child taps on the screen."""

from __future__ import annotations

from ..schema.publish import PublishTopic

TEMPLATE = """你在一张儿童绘本视频的画面上，帮孩子认出他手指点的地方是什么。

【这本书可以讲的东西】
__TOPICS__

【当前页码】
第 __PAGE__ 页

【孩子点的位置】
横向 __X__%，纵向 __Y__%，左上角是 0，右下角是 100。图上的圆圈是手指的位置。

规则：
1. 先看圆圈指着的是什么，再从上面的清单里选一条最贴切的。
2. 圆圈指着的是清单以外的普通东西，返回 {"id": "none"}。
3. 同时给出这个东西在画面里的外框，写成 [左, 上, 右, 下] 四个 0 到 1 的小数，
   框住它的完整形状，不要只框住圆圈。
4. 外框拿不准就写空数组 []。
5. 只输出 JSON，不要解释。两种形态：
   {"id": "t1", "box": [0.30, 0.45, 0.62, 0.88]}
   {"id": "none", "box": []}
"""


def touch_prompt(
    topics: list[PublishTopic],
    page: int,
    x: float,
    y: float,
) -> str:
    """Build the prompt that names what was tapped."""
    text = TEMPLATE.replace("__TOPICS__", _topics_text(topics))
    text = text.replace("__PAGE__", str(page))
    text = text.replace("__X__", str(round(x * 100)))
    return text.replace("__Y__", str(round(y * 100)))


# One line per candidate: what to look for, and the names it also goes by.
def _topics_text(topics: list[PublishTopic]) -> str:
    lines = []
    for topic in topics:
        names = "、".join(topic.aliases)
        tail = f"（也叫 {names}）" if names else ""
        look = topic.visual or topic.name
        lines.append(f"{topic.id} {topic.name}｜{look}{tail}")
    return "\n".join(lines) or "（没有可讲的东西）"
