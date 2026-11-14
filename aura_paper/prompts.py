"""
Prompt templates for model calls.
"""

_LAYOUT_NOTES = {
    "single": "这是一页单页画面。",
    "spread": "这是一张跨页画面，包含左右两页，请按从左到右的顺序阅读和描述画面。",
}

_PAGE_TEMPLATE = """你是一名儿童绘本内容理解助手。

请阅读这一页绘本，严格按下面的 JSON 结构输出：

{
  "page_text": "页面中的全部文字，保留原文与换行",
  "description": "用 2-4 句话描述画面：地点、角色、动作、氛围",
  "mood": "本页情绪，不超过 8 个字"
}

要求：
1. 只输出 JSON，不要解释文字，不要使用代码块。
2. 所有内容使用中文。
3. page_text 保留原文的标点与换行，用 \\n 表示换行；画面中没有文字时填空字符串。
4. 画面中看不到的信息不要编造。
5. __LAYOUT__
"""


def page_prompt(kind: str = "single") -> str:
    """Build the prompt for one page, aware of single or spread layout."""
    note = _LAYOUT_NOTES.get(kind, _LAYOUT_NOTES["single"])
    return _PAGE_TEMPLATE.replace("__LAYOUT__", note)
