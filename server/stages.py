"""Run one stage script and stream its output line by line."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from aura_paper.schema.time import now_iso
from aura_paper.store.books import set_title

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "data" / "books"
OUT = ROOT / "out"

# Page order, and the files that prove a stage has finished.
STAGE_FILES = {
    "ingest": ["ingest.json"],
    "understand": ["understand.json"],
    "crop": ["crop.json"],
    "assets": ["cast.json"],
    "identify": ["identify.json"],
    "storyboard": ["shots.json"],
    "voice": ["voice.json"],
    "jobs": ["jobs.json"],
    "render": ["render.json"],
    "compose": ["compose.json"],
    "subtitles": ["subtitles.json"],
    "show": ["show.json"],
}

# A stage is runnable once its script exists.
RUNNABLE = {
    stage
    for stage in STAGE_FILES
    if (ROOT / "scripts" / f"run_{stage}.py").is_file()
}

# One run per book at a time, so two clicks cannot wipe the same pages.
RUNNING: dict[str, str] = {}

# Every stage keeps its last run here, so the page can show all of them.
STAGES_NAME = "stages.json"

router = APIRouter(prefix="/api", tags=["stages"])


@router.post("/books/{book_id}/stages/{stage}/run")
async def run_stage(book_id: str, stage: str) -> dict:
    """Start one stage for a book and answer without waiting for it."""
    if stage not in RUNNABLE:
        raise HTTPException(status_code=501, detail="这个阶段还没接入")
    source = BOOKS / book_id / "source.pdf"
    if not source.is_file():
        raise HTTPException(status_code=404, detail="没有这本书的 PDF")
    if book_id in RUNNING:
        raise HTTPException(status_code=409, detail="这本书已经在运行")

    folder = OUT / book_id
    previous = _previous_stage(stage)
    if previous and _state(folder, previous, _stages(folder)) != "done":
        raise HTTPException(status_code=412, detail=f"先完成 {previous}")

    log = folder / "logs" / f"{stage}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")
    stages = _stages(folder)
    stages[stage] = {"state": "running", "started_at": now_iso()}
    _write_stages(folder, stages)

    RUNNING[book_id] = stage
    argv = _command(stage, book_id, source)
    asyncio.create_task(_watch(book_id, stage, argv, log, folder))
    return {"stage": stage, "log": str(log.relative_to(ROOT))}


@router.get("/books/{book_id}/stages")
def stage_states(book_id: str) -> dict:
    """Return one state per stage, read from the files a run leaves."""
    folder = OUT / book_id
    stages = _stages(folder)
    rows = []
    for stage in STAGE_FILES:
        log = folder / "logs" / f"{stage}.log"
        rows.append(
            {
                "stage": stage,
                "state": _state(folder, stage, stages),
                "log": log.is_file(),
                "runnable": stage in RUNNABLE,
                "ended_at": _record(stages, stage).get("ended_at", ""),
                "seconds": _record(stages, stage).get("seconds", 0),
            }
        )
    return {"stages": rows}


@router.get("/books/{book_id}/stages/{stage}/log")
def stage_log(book_id: str, stage: str) -> dict:
    """Return the output of the last run, empty when there is none."""
    log = OUT / book_id / "logs" / f"{stage}.log"
    if not log.is_file():
        return {"text": ""}
    return {"text": log.read_text(encoding="utf-8", errors="replace")}


@router.get("/books/{book_id}/stages/{stage}/events")
async def stage_events(book_id: str, stage: str) -> StreamingResponse:
    """Replay the log, then keep sending new lines until the run ends."""
    log = OUT / book_id / "logs" / f"{stage}.log"
    return StreamingResponse(
        _tail(log),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


# Move old records and mark runs cut short by a restart as failed.
def prepare_state() -> None:
    """Bring the stored stage records in line with this process."""
    for folder in OUT.glob("*/"):
        if not folder.is_dir():
            continue
        _absorb_run_json(folder)
        _close_stale(folder)


# The book id picks the PDF, so a wrong id cannot touch another book.
def _command(stage: str, book_id: str, source: Path) -> list[str]:
    script = str(ROOT / "scripts" / f"run_{stage}.py")
    root = str(OUT)
    if stage == "ingest":
        return [
            sys.executable,
            script,
            str(source),
            "--id",
            book_id,
            "--root",
            root,
        ]
    return [sys.executable, script, book_id, "--root", root]


# The stage before this one in page order, empty for the first.
def _previous_stage(stage: str) -> str:
    order = list(STAGE_FILES)
    index = order.index(stage)
    if index == 0:
        return ""
    return order[index - 1]


# Copy the child's output into the log, then record how it ended.
async def _watch(
    book_id: str,
    stage: str,
    argv: list[str],
    log: Path,
    folder: Path,
) -> None:
    began = time.perf_counter()
    started = now_iso()
    code = 1
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        with log.open("a", encoding="utf-8") as sink:
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                sink.write(raw.decode("utf-8", "replace"))
                sink.flush()
        code = await process.wait()
    except OSError as exc:
        with log.open("a", encoding="utf-8") as sink:
            sink.write(f"cannot start the script: {exc}\n")
    finally:
        with log.open("a", encoding="utf-8") as sink:
            sink.write(f"退出码 {code}\n")
        _record_run(folder, stage, code, started, began)
        if stage == "understand" and code == 0:
            _adopt_title(folder, book_id)
        RUNNING.pop(book_id, None)


# Understand reads the real title, so the library takes it over.
def _adopt_title(folder: Path, book_id: str) -> None:
    path = folder / "understand.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    title = str(data.get("title") or "").strip()
    set_title(book_id, title)


# Send each complete line once, and stop after the exit line.
async def _tail(log: Path):
    sent = 0
    while True:
        if log.exists():
            size = log.stat().st_size
            if size > sent:
                with log.open("rb") as handle:
                    handle.seek(sent)
                    chunk = handle.read(size - sent)
                sent = size
                for line in chunk.decode("utf-8", "replace").splitlines():
                    yield f"data: {json.dumps(line)}\n\n"
                    if line.startswith("退出码"):
                        return
        await asyncio.sleep(0.2)


# run.json 的旧记录并进 stages.json，每个阶段各留一条。
def _record_run(
    folder: Path,
    stage: str,
    code: int,
    started: str,
    began: float,
) -> None:
    stages = _stages(folder)
    stages[stage] = {
        "state": "done" if code == 0 else "failed",
        "exit": code,
        "started_at": started,
        "ended_at": now_iso(),
        "seconds": round(time.perf_counter() - began, 1),
    }
    _write_stages(folder, stages)


# Read every stage record of one book.
def _stages(folder: Path) -> dict:
    path = folder / STAGES_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_stages(folder: Path, stages: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / STAGES_NAME
    path.write_text(json.dumps(stages, indent=2), encoding="utf-8")


# One stage's record, empty when it never ran.
def _record(stages: dict, stage: str) -> dict:
    record = stages.get(stage)
    if not isinstance(record, dict):
        return {}
    return record


# 运行中看阶段记录，跑完的以产物为准。
def _state(folder: Path, stage: str, stages: dict) -> str:
    record = _record(stages, stage)
    if record.get("state") == "running":
        return "running"
    for name in STAGE_FILES[stage]:
        if (folder / name).is_file():
            return "done"
    if record.get("state") == "failed":
        return "failed"
    return "idle"


# An older book still keeps its last run in run.json.
def _absorb_run_json(folder: Path) -> None:
    old = folder / "run.json"
    if not old.is_file():
        return
    try:
        record = json.loads(old.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    stage = record.get("stage")
    if isinstance(stage, str) and stage:
        record.pop("stage", None)
        stages = _stages(folder)
        stages.setdefault(stage, record)
        _write_stages(folder, stages)
    old.unlink(missing_ok=True)


# A record left as running cannot belong to this process any more.
def _close_stale(folder: Path) -> None:
    stages = _stages(folder)
    changed = False
    for record in stages.values():
        if not isinstance(record, dict):
            continue
        if record.get("state") != "running":
            continue
        record["state"] = "failed"
        record["exit"] = -1
        record["ended_at"] = now_iso()
        changed = True
    if changed:
        _write_stages(folder, stages)
