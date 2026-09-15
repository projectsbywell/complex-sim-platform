"""In-memory per-IP rate limiting middleware (fixed 60s sliding window).

Applies to every HTTP request except a small exempt list (health probes and
swagger routes). Returns ``429 + retry-after`` when the budget is exhausted.

A reusable ``WindowGuard`` is exposed for WebSocket message throttling.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Optional

logger = logging.getLogger("complex_sim.ratelimit")

_429_BODY = json.dumps(
    {
        "detail": "Rate limit exceeded: 100 requests per minute per IP",
        "limit": 100,
        "retry_after_seconds": 60,
    }
).encode("utf-8")


class WindowGuard:
    """Sliding-window rate guard keyed by arbitrary string keys."""

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit = max(1, int(limit))
        self.window = max(1.0, float(window))
        self._hits: dict[str, "deque[float]"] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits.get(key)
            if dq is None:
                dq = deque()
                self._hits[key] = dq
            while dq and now - dq[0] >= self.window:
                dq.popleft()
            if len(dq) >= self.limit:
                return False
            dq.append(now)
            self._prune_locked(now)
            return True

    def _prune_locked(self, now: float) -> None:
        # Opportunistically drop dead keys so the table cannot grow forever.
        if len(self._hits) < 4096:
            return
        for key in [k for k, dq in self._hits.items() if not dq]:
            del self._hits[key]
        for key in [k for k, dq in self._hits.items() if dq and now - dq[-1] >= self.window * 2]:
            del self._hits[key]

    def active_keys(self) -> int:
        with self._lock:
            return len(self._hits)


class RateLimitMiddleware:
    """ASGI middleware: reject abusive per-IP request rates with HTTP 429."""

    def __init__(
        self,
        app,
        per_minute: int = 100,
        exempt: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.per_minute = per_minute
        self.exempt = set(exempt)
        self._guard = WindowGuard(limit=per_minute, window=60.0)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _client_ip(scope) -> str:
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-forwarded-for":
                first = value.decode("latin-1", "replace").split(",")[0].strip()
                if first:
                    return first
        client = scope.get("client")
        if client:
            return str(client[0])
        return "unknown"

    async def _deny(self, scope, send, ip: str, path: str) -> None:
        logger.warning(
            "rate_limit_exceeded",
            extra={"ip": ip, "path": path, "reason": "429"},
        )
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", b"60"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _429_BODY})

    # -- ASGI entry point ----------------------------------------------------
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self.exempt:
            await self.app(scope, receive, send)
            return
        ip = self._client_ip(scope)
        if not self._guard.allow(f"http:{ip}"):
            await self._deny(scope, send, ip, path)
            return
        await self.app(scope, receive, send)