"""App factory: API + static frontend, local-only hardening, seed import and the background worker."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import api, config
from .db import Database
from .jobs import Worker
from .seed import seed_if_needed

log = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def create_app(
    data_dir: Path = config.DEFAULT_DATA_DIR,
    *,
    fake: bool = False,
    start_worker: bool = True,
    seed: bool = True,
) -> FastAPI:
    db = Database(Path(data_dir) / "hookline.db")
    worker = Worker(db, fake=fake)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if seed:
            seed_if_needed(db)
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.stop()

    app = FastAPI(title="Hookline", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    app.state.worker = worker
    app.state.fake = fake

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # The API holds an API key and can spend quota, so refuse state-changing requests from other sites.
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin != f"http://{request.headers.get('host', '')}":
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site requests are not allowed."}, status_code=403)
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # Blocks DNS-rebinding: only requests addressed to this machine by loopback name are served.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    app.include_router(api.router)
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True, check_dir=False), name="static")
    return app
