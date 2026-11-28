"""Pipeline stages in run order, and the files each writes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    """One pipeline step, data only."""

    key: str  # fixed id, also the name of scripts/run_<key>.py
    name: str  # Chinese name of the stage
    description: str  # what the stage does
    per_page: bool  # the stage works page by page
    outputs: tuple[str, ...] = ()  # under output/<book_id>/


STAGES = (
    Stage(
        key="ingest",
        name="入库",
        description="把 PDF 渲染成源页，对开的两张并成一页、宽页拆成两页，再切出封面",
        per_page=True,
    ),
    Stage(
        key="read",
        name="读页",
        description="逐页读图，写下文字、分格框、形象外观与光照，封面另读书名与作者",
        per_page=True,
    ),
    Stage(
        key="crop",
        name="裁切",
        description="按分格框裁出画面，擦掉格内印刷文字，再切出每个形象的小图",
        per_page=True,
    ),
    Stage(
        key="cast",
        name="选角",
        description="把全书的形象归并成角色，定外观、挑参考图、分配音色",
        per_page=False,
    ),
    Stage(
        key="scout",
        name="勘景",
        description="把分格归并成场地，为每个场地挑一张背景图，并描述全书画风",
        per_page=False,
    ),
    Stage(
        key="identify",
        name="认人",
        description="判断只露局部或被遮挡的形象属于哪个角色",
        per_page=True,
    ),
    Stage(
        key="direct",
        name="分镜",
        description="分格编成场与镜头，规划每镜的动作与衔接，分配旁白与对白",
        per_page=True,
    ),
    Stage(
        key="record",
        name="配音",
        description="按选定的音色逐句合成语音，测出每句的实际时长",
        per_page=True,
    ),
    Stage(
        key="prepare",
        name="备料",
        description="把台词铺成这镜的音轨，并写出这一镜的镜头清单",
        per_page=True,
    ),
    Stage(
        key="render",
        name="生成",
        description="按镜头清单逐镜调用视频模型，生成原片",
        per_page=True,
    ),
    Stage(
        key="mix",
        name="混音",
        description="把原片与本镜音轨合成一次镜次",
        per_page=True,
    ),
    Stage(
        key="audit",
        name="审片",
        description="检查镜次的画面与声音问题并打分",
        per_page=True,
    ),
    Stage(
        key="assemble",
        name="合片",
        description="做出片头，把选定的镜次按顺序接成片",
        per_page=False,
    ),
    Stage(
        key="subtitle",
        name="配字幕",
        description="把每句台词对齐到成片时间轴，写出字幕文件",
        per_page=False,
    ),
)
