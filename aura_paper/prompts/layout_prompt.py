"""Prompt that asks whether one image is one picture or two pages."""

TEMPLATE = """你是一名儿童绘本排版助手。

一张扫描图里可能并排放着左右两页，也可能是一整幅画面横跨左右。

只输出 JSON，不要解释文字，不要使用代码块：
{
  "two_pages": true 或 false,
  "reason": "判断依据，不超过 20 字"
}

判断依据：
1. 左右各自成页：中间有装订缝或明显的分界，左右两半各有自己的画面和留白。
   这时 two_pages 为 true。
2. 一整幅画面：画面跨过中线连成一片，中间没有断开，也没有分界。
   这时 two_pages 为 false。
3. 拿不准时按一整幅处理。
"""


def layout_prompt() -> str:
    """Build the prompt that asks one image's layout."""
    return TEMPLATE
