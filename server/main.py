"""Build the web app: two pages, shared files and the book API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from aura_paper.config import load_env

from .books import router
from .qa import router as qa_router
from .qa import socket_router
from .stages import prepare_state
from .stages import router as stages_router

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
FONTS = ROOT / "resources" / "fonts"
OUT = ROOT / "out"


def create_app() -> FastAPI:
    """Return the app with both pages and the API mounted."""
    app = FastAPI(title="灵动绘卷")
    app.middleware("http")(_revalidate)
    load_env(ROOT / ".env")
    prepare_state()

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Send a bare host to the reader."""
        return RedirectResponse("/reader/")

    app.include_router(router)
    app.include_router(stages_router)
    app.include_router(qa_router)
    app.include_router(socket_router)
    app.mount(
        "/static/fonts",
        StaticFiles(directory=FONTS, check_dir=False),
        name="fonts",
    )
    app.mount(
        "/static",
        StaticFiles(directory=WEB / "static"),
        name="static",
    )
    app.mount(
        "/studio",
        StaticFiles(directory=WEB / "studio", html=True),
        name="studio",
    )
    app.mount(
        "/reader",
        StaticFiles(directory=WEB / "reader", html=True),
        name="reader",
    )
    app.mount(
        "/media",
        StaticFiles(directory=OUT, check_dir=False),
        name="media",
    )
    return app


# Pages and their CSS/JS change while the server runs, so the browser must
# revalidate them instead of reusing a stale copy from its cache.
async def _revalidate(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".css", ".js", ".html", "/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


app = create_app()
