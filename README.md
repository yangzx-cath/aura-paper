# AuraPaper · 灵动绘卷

把一本纸质绘本的 PDF 做成带配音、带字幕的动画短片，并交给阅读端按书播放。

- 输入：`data/books/<id>/source.pdf`
- 输出：`data/books/<id>/pub/`（成片、字幕、封面、发布清单）

## 环境

- Python 3.11 以上
- 系统里有 `ffmpeg` 和 `ffprobe`

```bash
python -m venv .venv
.venv/bin/pip install -e ".[web,dev]"
```

字幕烧进画面要先下载字体：`scripts/get_fonts.sh`（默认不烧）。

## 配置

密钥都放在仓库根目录的 `.env`，由 `aura_paper/config.py::load_env` 读入。

| 变量 | 用途 |
| --- | --- |
| `LLM_API_KEY` `LLM_BASE_URL` `LLM_MODEL` | 读图、写分镜、认人 |
| `ARK_API_KEY` `SEEDANCE_*` | 生成视频片段 |
| `AURA_VIDEO_PROVIDER` | `seedance`（默认）或 `minimax` |
| `MINIMAX_*` | 只有用 MiniMax 出片时才需要 |
| `TTS_API_KEY` `TTS_RESOURCE_ID` | 配音 |
| `ASR_*` | 阅读端的语音指令 |

目录也能换：`AURA_OUT_DIR`、`AURA_BOOKS_DIR`、`AURA_CACHE_DIR`。

## 目录布局

| 路径 | 内容 |
| --- | --- |
| `aura_paper/stages/` | 十二个阶段的实现，一个阶段一个文件 |
| `aura_paper/schema/` | 每个 JSON 产物的读写契约 |
| `aura_paper/prompts/` | 各阶段用的提示词 |
| `aura_paper/clients/` | LLM、视频、TTS、ASR 四类客户端 |
| `aura_paper/media/` | 图像、音频、ffmpeg 与 ffprobe 封装 |
| `aura_paper/store/` | 产物写入、书库记录、缓存 |
| `scripts/` | 每个阶段一个命令行入口 `run_<stage>.py` |
| `server/` | FastAPI 适配层：书库、阶段运行、阅读端语音 |
| `web/studio/` | 处理端页面：跑阶段、看日志 |
| `web/reader/` | 阅读端页面：书库与播放器 |
| `web/static/shared/` | 两个页面共用的 CSS 变量与版式 |
| `resources/fonts/` | 烧字幕用的字体 |
| `out/<id>/` | 工作目录，阶段的中间产物都在这里 |
| `data/books/<id>/` | 书库：`source.pdf`、`book.json`、`pub/` |
| `data/recordings/` | 阅读端录下的语音 |

`out/` 可以随时删，`pub/` 是唯一需要长期保留的东西。

## 跑一本书

命令行要在**仓库根目录**运行，脚本按当前目录找 `out/` 和 `data/books/`。

```bash
.venv/bin/python scripts/run_ingest.py data/books/B005/source.pdf --id B005
for stage in understand crop assets identify storyboard voice jobs \
             render compose subtitles publish; do
  .venv/bin/python scripts/run_$stage.py B005
done
```

## 阶段

| 阶段 | 产物 | 调用外部接口 |
| --- | --- | --- |
| `ingest` 拆页 | `ingest.json`、`pages/` | 是 |
| `understand` 理解 | `understand.json` | 是（每页一次） |
| `crop` 切图 | `crop.json`、`panels/`、`figures/` | 否 |
| `assets` 出图 | `cast.json`、`locations.json` | 是 |
| `identify` 认人 | `identify.json` | 是 |
| `storyboard` 分镜 | `scenes.json`、`shots.json` | 是（两次） |
| `voice` 配音 | `voice.json`、`voice/` | 是（TTS） |
| `jobs` 镜次 | `jobs.json`、`jobs/` | 否 |
| `render` 出镜 | `render.json`、`clips/` | 是（每个镜头一次） |
| `compose` 成片 | `compose.json`、`shots/` | 片头一次 TTS，有缓存 |
| `subtitles` 字幕 | `subtitles.json`、`subtitles.ass`、`subtitles.vtt` | 否 |
| `publish` 发布 | `data/books/<id>/pub/` | 否 |

`ingest`、`understand`、`assets`、`identify`、`storyboard`、`voice`、
`render`、`compose` 会产生费用，其余阶段只在本地跑。

几个常用参数：

```bash
python scripts/run_render.py B005 --shot j3      # 只出一镜
python scripts/run_subtitles.py B005 --burn      # 另烧一份带字幕的成片
python scripts/run_publish.py C01 --as B001      # 把 C01 的产物发布成 B001
python scripts/run_jobs.py B005 --resolution 1080p --ratio 4:3
```

## 服务

```bash
.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
```

- `/studio/` 处理端：上传 PDF，按顺序跑十二个阶段，看每行的日志
- `/reader/` 阅读端：书库列表，点进去播成片，字幕来自 VTT
- `/api/books`、`/api/books/<id>/stages`、`/api/books/<id>/publish`、
  `/api/books/<id>/pub/<film.mp4|subtitles.vtt|cover.jpg>`

阶段的可用性在导入时算一次，改了 `scripts/` 下的文件要重启服务。
页面与静态文件带 `Cache-Control: no-cache`，改动后普通刷新即可。

## 测试与风格

```bash
.venv/bin/python -m pytest tests -q
```

- 行宽 79，black / isort 配置在 `pyproject.toml`
- 阶段名 = 脚本名 = 产物名：`stages/crop.py`、`run_crop.py`、`crop.json`
- 测试只覆盖真实运行看不出来的地方：错误路径、边界、解析
