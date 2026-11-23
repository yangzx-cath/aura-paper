"""Prompt that asks whether one image is one picture or two pages."""

TEMPLATE = """你是一名儿童绘本排版助手。

一张扫描图里可能并排放着左右两页，也可能是一整幅画面横跨左右。

只输出 JSON，不要解释文字，不要使用代码块：
{
  "two_pages": true 或 false,
  "reason": "判断依据，不超过 20 字"
}

判断依据：
1. 画出来的东西（人物、道具、背景里画出来的景物）压过中线、一直连到另一半，中间
   没有断开，就是一整幅画面跨页，two_pages 为 false。
2. 跨中线的只有纸的底色（白纸、纯色底），两半的景物互不相接，就是两页，two_pages
   为 true。
3. 小图多的版式看得更清楚：两半各自都有好几块独立的小画，按两页算。
4. 拿不准时按一整幅处理——整页后面还会按画面内容拆成小块。
"""


def layout_prompt() -> str:
    """Build the prompt that asks one image's layout."""
    return TEMPLATE
