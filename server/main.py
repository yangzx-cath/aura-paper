"""Serve the pages in web/ and the files they load."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from aura_paper.config import load_env, output_root

from .books import router as books_router
from .stages import router as stages_router

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

load_env(ROOT / ".env")

app = FastAPI(title="灵动绘卷")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send a bare host to a page instead of a 404."""
    return RedirectResponse("/studio/")


app.include_router(books_router)
app.include_router(stages_router)
app.mount(
    "/studio",
    StaticFiles(directory=WEB / "studio", html=True),
    name="studio",
)
app.mount(
    "/media",
    StaticFiles(directory=output_root(), check_dir=False),
    name="media",
)
