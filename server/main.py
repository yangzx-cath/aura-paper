"""Build the web app: two pages, shared files and the book API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .books import router
from .stages import close_stale_runs
from .stages import router as stages_router

WEB = Path(__file__).resolve().parent.parent / "web"
FONTS = Path(__file__).resolve().parent.parent / "resources" / "fonts"


def create_app() -> FastAPI:
    """Return the app with both pages and the API mounted."""
    app = FastAPI(title="灵动绘卷")
    app.middleware("http")(_revalidate)
    close_stale_runs()

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Send a bare host to the reader."""
        return RedirectResponse("/reader/")

    app.include_router(router)
    app.include_router(stages_router)
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


# Pages and their CSS/JS change while the server runs, so the browser must
# revalidate them instead of reusing a stale copy from its cache.
async def _revalidate(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".css", ".js", ".html", "/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


app = create_app()
