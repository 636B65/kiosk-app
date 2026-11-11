"""FastAPI app skeleton shared by every service."""

import logging
import os
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kiosk_common.config import ServiceConfig
from kiosk_common.http import UpstreamError


def _release_info() -> dict:
    """Version and commit baked into the image (or APP_VERSION / GIT_COMMIT)."""
    import json

    info = {"version": "", "commit": ""}
    path = os.environ.get("RELEASE_FILE", "/app/release.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        info.update({k: str(data.get(k) or "") for k in info})
    except (OSError, ValueError):
        pass
    return {
        "version": os.environ.get("APP_VERSION") or info["version"] or "dev",
        "commit": os.environ.get("GIT_COMMIT") or info["commit"],
    }


def create_base_app(config: ServiceConfig, title: str, lifespan: Callable | None = None) -> FastAPI:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    # One line per service-to-service call is too chatty at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = FastAPI(title=title, lifespan=lifespan)
    app.state.config = config
    app.state.database = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(UpstreamError)
    async def upstream_error(request: Request, exc: UpstreamError):
        if exc.unreachable or exc.status >= 500:
            logging.getLogger(config.service_name).error("upstream failure: %s", exc)
            return JSONResponse(
                status_code=502,
                content={"detail": f"The {exc.service} is not available right now. Try again."},
            )
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok", "service": config.service_name, **_release_info()}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        database = app.state.database
        if database is not None and not database.ping():
            return JSONResponse(status_code=503, content={"status": "database unavailable"})
        return {"status": "ok", "service": config.service_name}

    return app
