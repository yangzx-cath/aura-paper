"""Prompt that turns one shot into a video request."""

from __future__ import annotations

from ..schema.cast import Cast
from ..schema.job import JobImage, JobLine
from ..schema.shot import Shot

TEMPLATE = """这是一本儿童绘本的一镜动画。

【画风】
__STYLE__

【场地】
__PLACE__

【出场角色】
__CAST__

【这一镜要发生的事】
__BEATS__

【参考图】
__IMAGES__

__SCRIPT__【要求】
1. 画风、角色的长相和衣着、场地，都要跟参考图一致；不要换装，不要加人，
   也不要演这一镜没有写到的动作。
2. 画面里的物件（积木、玩具、道具等）从开头到结尾保持同一形状、颜色和数量：
   被拿起的物件一直看得见，被放下的物件留在画面里；不要变形、不要凭空消失、
   不要凭空出现，也不要被角色吃掉或吞下（除非这一镜的动作里明确写到）。
3. 参考图是分格画面，按上面的顺序连成一个连续镜头，不要做成拼贴或分格画。
4. 参考图上的字不要画进视频：印刷体的正文、拟声词的美术字都只属于参考图。
5. 画面铺满整个画幅，四周不要留白边，不要出现色块。
6. 景别是__CAMERA__，__MOVE__。
7. __SOUND__
8. 图注里写了这一格是谁、露出哪些部位，按图注认人，不要换人。
9. 这一镜大约 __SECONDS__ 秒，动作要在这个长度内做完。
10. 保持无字幕：视频全程不出现任何文字、字幕、气泡、Logo、水印。
"""

# How the camera behaves for each framing the storyboard can pick.
MOVES = {
    "全景": "角色全身都要在画面里，能看到周围环境",
    "中景": "拍到膝盖以上，环境露一部分",
    "近景": "拍到胸部以上，环境只当背景",
    "特写": "只拍脸或手上一件东西，环境几乎不出现",
}


def job_prompt(
    shot: Shot,
    *,
    style: str,
    place: str,
    cast: list[Cast],
    images: list[JobImage],
    seconds: int,
    audio: bool,
) -> str:
    """Build the prompt for one shot's video request."""
    return _build(
        shot,
        style=style,
        place=place,
        cast=cast,
        images=images,
        seconds=seconds,
        sound=_sound_text(audio, shot),
        script="",
    )


def audio_prompt(
    shot: Shot,
    *,
    style: str,
    place: str,
    cast: list[Cast],
    images: list[JobImage],
    lines: list[JobLine],
    seconds: int,
    quiet: bool = False,
    voice_only: bool = False,
) -> str:
    """Build the prompt for a shot whose voice track is sent as reference."""
    return _build(
        shot,
        style=style,
        place=place,
        cast=cast,
        images=images,
        seconds=seconds,
        sound=_track_text(quiet, voice_only),
        script=_script_text(cast, lines, voice_only),
    )


# Fill the template with the parts every prompt shares.
def _build(
    shot: Shot,
    *,
    style: str,
    place: str,
    cast: list[Cast],
    images: list[JobImage],
    seconds: int,
    sound: str,
    script: str,
) -> str:
    text = TEMPLATE.replace("__STYLE__", style or "（未指定，按参考图的画法）")
    text = text.replace(
        "__PLACE__", place or "（没有场地母图，按分格画面里的环境）"
    )
    text = text.replace("__CAST__", _cast_text(cast))
    text = text.replace("__BEATS__", _beats_text(shot))
    text = text.replace("__IMAGES__", _images_text(images))
    text = text.replace("__SCRIPT__", script)
    text = text.replace("__CAMERA__", shot.camera or "中景")
    text = text.replace("__MOVE__", MOVES.get(shot.camera, MOVES["中景"]))
    text = text.replace("__SOUND__", sound)
    return text.replace("__SECONDS__", str(seconds))


# Say that the wording and the order come from the sent track.
def _track_text(quiet: bool = False, voice_only: bool = False) -> str:
    said = "声音照音频1：谁说话、说什么、按什么顺序，都不改。"
    if voice_only:
        said += "音频1 没有人声的段落，画面里也不许有任何人说话。"
        said += "每一句都要说完，不要说到一半就停。"
    else:
        said += "画外音时谁都不张口。"
    if quiet:
        said += "整段不要生成任何音效、音乐和环境声。"
    return said


# List who speaks, in order. The words come from the track, so they are not
# repeated here: a text-capable model would draw them on the picture.
def _script_text(
    cast: list[Cast],
    lines: list[JobLine],
    voice_only: bool = False,
) -> str:
    if not lines:
        return ""
    names = {member.id: member.name or member.id for member in cast}
    said = []
    for number, line in enumerate(lines, start=1):
        if line.kind == "音效":
            said.append(f"{number}. 音效，照音频1 出声，不要写成字")
        elif line.kind == "对白" and line.cast:
            who = names.get(line.cast, line.cast)
            said.append(f"{number}. {who}说，{who}的口型对上音频1")
        elif voice_only:
            said.append(f"{number}. 这一段没有人声，只演画面动作")
        else:
            said.append(f"{number}. 画外音，画面上的人不张口")
    body = "\n".join(said)
    if voice_only:
        intro = (
            "【配音】\n"
            "音频1 只在对白处有人声，其余时段是空的。\n"
            "人声照音频1，顺序照音频1；空的时段不许说话，也不许把台词写到\n"
            "画面上。\n"
        )
    else:
        intro = (
            "【配音】\n"
            "音频1 是本镜的配音，台词的字由音频1 念，不要写到画面上。\n"
            "说话的顺序、人声和节奏都照音频1，不要自己另写台词或多说话。\n"
        )
    return f"{intro}{body}\n\n"


# Say what the sound of the shot should be.
def _sound_text(audio: bool, shot: Shot) -> str:
    if not audio:
        return "这一镜不需要声音，只要画面。"
    effects = [line.text for line in shot.audio if line.kind == "音效"]
    if not effects:
        return "只留环境和动作的声音，不要出现人说话的声音。"
    listed = "、".join(effects)
    return f"只留环境和动作的声音（比如{listed}），" "不要出现人说话的声音。"


# List the characters that appear, with the look they must keep.
def _cast_text(cast: list[Cast]) -> str:
    lines = []
    for member in cast:
        name = member.name or member.id
        lines.append(f"{name}：{member.look}")
    return "\n".join(lines) or "（这一镜没有角色出场）"


# List what has to happen, in order.
def _beats_text(shot: Shot) -> str:
    lines = []
    for number, beat in enumerate(shot.beats, start=1):
        lines.append(f"{number}. {beat}")
    if shot.continuity:
        lines.append(f"这一镜接在上一镜之后：{shot.continuity}")
    return "\n".join(lines) or "（按参考图把动作自然延续下去）"


# Name every reference image so the prompt can point at it.
def _images_text(images: list[JobImage]) -> str:
    lines = []
    for number, image in enumerate(images, start=1):
        lines.append(f"图{number}：{image.note}")
    return "\n".join(lines) or "（没有参考图）"
