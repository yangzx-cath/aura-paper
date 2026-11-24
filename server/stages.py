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

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "data" / "books"
OUT = ROOT / "out"

# Only stages whose script takes a PDF path are runnable so far.
RUNNABLE = {"ingest"}

# Page order, and the files that prove a stage has finished.
STAGE_FILES = {
    "ingest": ["ingest.json"],
    "understand": ["understand.json"],
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

# One run per book at a time, so two clicks cannot wipe the same pages.
RUNNING: dict[str, str] = {}

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
    log = folder / "logs" / f"{stage}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps(
            {"stage": stage, "state": "running", "started_at": now_iso()}
        ),
        encoding="utf-8",
    )

    RUNNING[book_id] = stage
    argv = _command(stage, book_id, source)
    asyncio.create_task(_watch(book_id, stage, argv, log, folder))
    return {"stage": stage, "log": str(log.relative_to(ROOT))}


@router.get("/books/{book_id}/stages")
def stage_states(book_id: str) -> dict:
    """Return one state per stage, read from the files a run leaves."""
    folder = OUT / book_id
    run = _last_run(folder)
    rows = []
    for stage in STAGE_FILES:
        log = folder / "logs" / f"{stage}.log"
        rows.append(
            {
                "stage": stage,
                "state": _state(folder, stage, run),
                "log": log.is_file(),
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


# A run cut short by a server restart would otherwise stay running forever.
def close_stale_runs() -> None:
    """Mark runs left behind by a restart as failed."""
    for path in OUT.glob("*/run.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("state") != "running":
            continue
        data["state"] = "failed"
        data["exit"] = -1
        data["ended_at"] = now_iso()
        path.write_text(json.dumps(data), encoding="utf-8")


# The book id picks the PDF, so a wrong id cannot touch another book.
def _command(stage: str, book_id: str, source: Path) -> list[str]:
    script = ROOT / "scripts" / f"run_{stage}.py"
    return [
        sys.executable,
        str(script),
        str(source),
        "--id",
        book_id,
        "--root",
        str(OUT),
    ]


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
        RUNNING.pop(book_id, None)


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


# run.json outlives the run, so it holds the last result and its times.
def _record_run(
    folder: Path,
    stage: str,
    code: int,
    started: str,
    began: float,
) -> None:
    data = {
        "stage": stage,
        "state": "done" if code == 0 else "failed",
        "exit": code,
        "started_at": started,
        "ended_at": now_iso(),
        "seconds": round(time.perf_counter() - began, 1),
    }
    (folder / "run.json").write_text(json.dumps(data), encoding="utf-8")


# Read the last run record, or an empty dict when there is none.
def _last_run(folder: Path) -> dict:
    path = folder / "run.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# 运行中照 run.json 的状态，跑完的以产物为准。
def _state(folder: Path, stage: str, run: dict) -> str:
    mine = run.get("stage") == stage
    if mine and run.get("state") == "running":
        return "running"
    for name in STAGE_FILES[stage]:
        if (folder / name).is_file():
            return "done"
    if mine and run.get("state") == "failed":
        return "failed"
    return "idle"
