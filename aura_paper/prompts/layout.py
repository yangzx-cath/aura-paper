"""How each page shape is described to the model."""

from __future__ import annotations

READING_NOTES = {
    "portrait": "这是一张竖幅画面。",
    "landscape": (
        "这是一张横幅画面。先看是一整幅图还是左右两页拼在一起；"
        "如果是两页，按从左到右的顺序阅读和描述。"
    ),
}

SHOT_NOTES = {
    "portrait": "这是一张竖幅画面，镜头保持稳定。",
    "landscape": "这是一张横幅画面，镜头从左到右缓慢平移。",
}


def reading_note(kind: str) -> str:
    """Return the reading note for one page shape."""
    return READING_NOTES.get(kind, READING_NOTES["portrait"])


def shot_note(kind: str) -> str:
    """Return the camera note for one page shape."""
    return SHOT_NOTES.get(kind, SHOT_NOTES["portrait"])
