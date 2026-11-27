"""Serve the pages in web/ and the files they load."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

app = FastAPI(title="灵动绘卷")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send a bare host to a page instead of a 404."""
    return RedirectResponse("/studio/")


app.mount(
    "/studio",
    StaticFiles(directory=WEB / "studio", html=True),
    name="studio",
)
