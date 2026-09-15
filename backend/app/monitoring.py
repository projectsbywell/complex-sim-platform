"""Structured JSON logging and an in-memory metrics registry.

Every log line is a single JSON document (one per line) — grep/parse friendly.
Metrics are simple counters/gauges/duration samples exposed by /metrics.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
import uuid
from typing import Any, Optional

LOG_NAME = "complex_sim"


class JsonFormatter(logging.Formatter):
    """Emit one compact JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in (
            "method",
            "path",
            "status",
            "duration_ms",
            "ip",
            "user",
            "request_id",
            "simulation_id",
            "kind",
            "role",
            "exc",
            "reason",
        ):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Install the JSON-lines handler once (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    logging.getLogger(LOG_NAME).setLevel(level.upper())


def get_logger(name: str = LOG_NAME) -> logging.Logger:
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Metrics registry
# ---------------------------------------------------------------------------


class MetricsRegistry:
    """Thread-safe counters, gauges and request-duration samples."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._durations_ms: dict[str, float] = {}
        self._n_durations: dict[str, int] = {}
        self._started = time.time()

    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + by

    def decr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] = max(0, self._counters.get(name, 0) - by)

    def observe(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self._durations_ms[name] = self._durations_ms.get(name, 0.0) + duration_ms
            self._n_durations[name] = self._n_durations.get(name, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            uptime = round(time.time() - self._started, 1)
            counters = dict(self._counters)
            durations = dict(self._durations_ms)
            n_dur = dict(self._n_durations)
        avg = {k: round(v / n_dur[k], 3) for k, v in durations.items() if n_dur.get(k)}
        return {
            "uptime_seconds": uptime,
            "counters": counters,
            "avg_duration_ms": avg,
        }


registry = MetricsRegistry()


# ---------------------------------------------------------------------------
# ASGI middlewares
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware:
    """Log every HTTP request as a JSON line and collect metrics.

    Paths are normalised back to route templates (e.g. ``/api/simulations/abc``
    becomes ``/api/simulations/{sim_id}``) so metric cardinality stays bounded.
    """

    def __init__(self, app, fastapi_app=None) -> None:
        self.app = app
        self._templates: list[Any] = []
        # ``app`` received here is the next middleware in the stack, not the
        # FastAPI app; the route table must come from the explicit reference.
        router = (
            getattr(fastapi_app, "router", None) if fastapi_app is not None else None
        )
        if router is None:
            router = getattr(app, "router", None)
        if router is not None:
            for route in getattr(router, "routes", []):
                # FastAPI>=0.139 wraps included routers in _IncludedRouter;
                # dig down to the original APIRouter's routes.
                nested = getattr(route, "original_router", None) or getattr(
                    route, "router", None
                )
                source = nested if nested is not None else None
                self._collect_templates(source or route)

    def _collect_templates(self, route) -> None:
        routes = getattr(route, "routes", None)
        if routes:  # a router: recurse into each sub-route
            for sub in routes:
                self._collect_templates(sub)
            return
        regex = getattr(route, "path_regex", None)
        template = getattr(route, "path", None)
        if regex is not None and template is not None:
            self._templates.append((re.compile(regex.pattern), template))

    def _template_for(self, path: str) -> str:
        for regex, template in self._templates:
            if regex.match(path):
                return template
        return path

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        path = scope.get("path", "")
        template = self._template_for(path)
        request_id = uuid.uuid4().hex[:12]
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        forwarded = self._xff(scope)
        if forwarded:
            ip = forwarded
        method = scope.get("method", "")
        status_holder: dict[str, Any] = {}

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            status = status_holder.get("status", 0)
            registry.incr("requests_total")
            registry.incr(f"status_{status}")
            if 500 <= status < 600:
                registry.incr("errors_5xx")
            if template and template.startswith(("/api/", "/ws/")):
                registry.incr("route." + template)
                registry.observe("route." + template, duration_ms)
            registry.incr("method." + method)
            logger = get_logger(LOG_NAME + ".access")
            logger.info(
                "request",
                extra={
                    "method": method,
                    "path": path,
                    "status": status,
                    "duration_ms": round(duration_ms, 2),
                    "ip": ip,
                    "request_id": request_id,
                },
            )

    @staticmethod
    def _xff(scope) -> Optional[str]:
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-forwarded-for":
                first = value.decode("latin-1", "replace").split(",")[0].strip()
                if first:
                    return first
        return None


class SecurityHeadersMiddleware:
    """Protective response headers (defense-in-depth for an API)."""

    _BASE = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "X-XSS-Protection": "1; mode=block",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    _API_CSP = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
        "form-action 'none'; sandbox"
    )
    _DOCS_CSP = (
        "default-src 'self'; script-src 'self' 'unsafe-inline' "
        "https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' "
        "https://cdn.jsdelivr.net; font-src 'self' data: https://cdn.jsdelivr.net; "
        "img-src 'self' data:; connect-src 'self'"
    )

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        is_docs = path.startswith("/docs") or path.startswith("/redoc")

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for key, value in self._BASE.items():
                    headers.append((key.encode("ascii"), value.encode("ascii")))
                csp = self._DOCS_CSP if is_docs else self._API_CSP
                headers.append((b"content-security-policy", csp.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
