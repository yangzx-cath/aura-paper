"""Prompt that asks whether a page holds two pages."""

from __future__ import annotations

TEMPLATE = """你是一名儿童绘本排版助手。

请判断这一张图片是一页，还是左右两页拼在一起的跨页。

只输出 JSON，不要解释文字，不要使用代码块：
{
  "spread": true 或 false,
  "reason": "判断依据，不超过 20 字"
}

判断依据：
1. 跨页：左右两半各有独立的画面、留白和边框，中间能看到装订缝，
   或者两半各自有自己的文字块或页码。
2. 单页：内容是一整幅跨过中线的画面；或者一页之内分成几个格子，
   画面和文字分散在格子里。格子版式仍然是一页。
3. 拿不准时按单页处理。
"""


def split_prompt() -> str:
    """Build the prompt that asks whether one page holds two pages."""
    return TEMPLATE
