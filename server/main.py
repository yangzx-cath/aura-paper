"""Build the web app: two pages, shared files and the book API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .books import router

WEB = Path(__file__).resolve().parent.parent / "web"
FONTS = Path(__file__).resolve().parent.parent / "resources" / "fonts"


def create_app() -> FastAPI:
    """Return the app with both pages and the API mounted."""
    app = FastAPI(title="灵动绘卷")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Send a bare host to the reader."""
        return RedirectResponse("/reader/")

    app.include_router(router)
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
    return app


app = create_app()
