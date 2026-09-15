"""Thread-safe in-memory LRU cache with TTL, used on GET endpoints.

Entries expire after ``default_ttl`` seconds (60s default) and the cache is
bounded by ``maxsize``. Expired entries are pruned lazily to keep hot paths
O(1)-ish.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Optional

from .config import settings

_MISS = object()


class LRUCache:
    def __init__(self, maxsize: int = 1024, default_ttl: float = 60.0) -> None:
        self.maxsize = max(1, int(maxsize))
        self.default_ttl = float(default_ttl)
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any:
        """Return the cached value or the ``_MISS`` sentinel."""
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return _MISS
            expires, value = item
            if expires <= now:
                del self._data[key]
                self.misses += 1
                return _MISS
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def put(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        expires = time.monotonic() + (ttl if ttl is not None else self.default_ttl)
        with self._lock:
            self._data[key] = (expires, value)
            self._data.move_to_end(key)
            self._prune_locked()

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                self._data.pop(k, None)
            return len(keys)

    def _prune_locked(self) -> None:
        now = time.monotonic()
        # Lazy expiry sweep: evict expired entries from the oldest end and
        # cap total size. Expired entries buried behind fresh ones are caught
        # by the maxsize eviction or the next sweep.
        scanned = 0
        for key in list(self._data):
            if scanned >= 64:
                break
            expires, _ = self._data[key]
            if expires <= now:
                del self._data[key]
                scanned += 1
            else:
                break
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "size": len(self._data),
                "maxsize": self.maxsize,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 4) if total else 0.0,
            }

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


cache = LRUCache(
    maxsize=settings.cache_maxsize,
    default_ttl=float(settings.cache_ttl_seconds),
)


def cached(key_fn: Optional[Callable[..., str]] = None, ttl: Optional[float] = None):
    """Decorator: cache a function's return value with the global LRUCache."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_fn(*args, **kwargs) if key_fn else f"{fn.__module__}.{fn.__qualname__}"
            hit = cache.get(key)
            if hit is not _MISS:
                return hit
            value = fn(*args, **kwargs)
            cache.put(key, value, ttl)
            return value

        return wrapper

    return decorator