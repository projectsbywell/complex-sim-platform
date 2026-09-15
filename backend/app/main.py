"""FastAPI application entry point.

Run with:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import datetime
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import monitoring, routes_auth, routes_sim, ws  # noqa: F401
from .cache import cache
from .config import settings
from .monitoring import (
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    get_logger,
    registry,
    setup_logging,
)
from .ratelimit import RateLimitMiddleware
from .sim_service import service
from .store import store

setup_logging(settings.log_level)
logger = get_logger()
_START = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "startup",
        extra={
            "version": settings.version,
            "simcore": service.simcore_info(),
            "storage": {
                "mode": settings.storage_backend(),
                "database_url_set": bool(settings.database_url),
                "data_dir": str(settings.data_dir),
            },
            "data": {
                "users": store.count_users(),
                "simulations": store.count_simulations(),
            },
        },
    )
    yield
    logger.info(
        "shutdown",
        extra={
            "uptime_seconds": round(time.time() - _START, 1),
            "requests_total": registry.snapshot()["counters"].get("requests_total", 0),
        },
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=settings.description,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Routes first, so middlewares that introspect the router (e.g. request
    # logging path normalisation) see the full route table.
    app.include_router(routes_auth.router)
    app.include_router(routes_sim.router)
    app.add_api_websocket_route("/ws/simulations/{sim_id}", ws.simulations_ws)

    # Middleware stack — last added is outermost:
    #   CORS (preflight) -> SecurityHeaders -> RequestLogging -> RateLimit -> routes
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=settings.rate_limit_per_minute,
        exempt=settings.rate_limit_exempt,
    )
    app.add_middleware(RequestLoggingMiddleware, fastapi_app=app)
    app.add_middleware(SecurityHeadersMiddleware)
    origins = list(settings.cors_origins)
    if "*" in origins:
        # wildcard + credentials is not valid per CORS spec
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )

    # -- ops endpoints -------------------------------------------------------
    @app.get("/health", tags=["ops"], summary="Liveness/readiness probe")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": settings.version,
            "uptime_seconds": round(time.time() - _START, 1),
            "simcore": service.simcore_info(),
            "storage": {
                "mode": settings.storage_backend(),
                "writable": settings.data_dir.exists(),
            },
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    @app.get("/metrics", tags=["ops"], summary="Simple JSON metrics")
    def metrics() -> dict[str, Any]:
        snap = registry.snapshot()
        snap["cache"] = cache.stats()
        all_sims = store.list_simulations()
        snap["simulations"] = {
            "total": len(all_sims),
            "steps_total": sum(s.steps_done for s in all_sims),
        }
        snap["users"] = store.count_users()
        snap["storage"] = {
            "mode": settings.storage_backend(),
            "database_url_set": bool(settings.database_url),
        }
        snap["simcore"] = service.simcore_info()
        return snap

    # -- exception handling ---------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            extra={"path": request.url.path, "exc": repr(exc)},
        )
        registry.incr("errors_5xx")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers={"X-Content-Type-Options": "nosniff"},
        )

    return app


app = create_app()