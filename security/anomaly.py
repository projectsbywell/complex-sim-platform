"""
anomaly.py — detecção de anomalias leve (z-score + taxa de requisições)
Sem dependências externas (stdlib + math). Estado em memória.
"""

from __future__ import annotations

import math
import time
from collections import deque, defaultdict
from typing import Dict, Deque, Optional


class AnomalyDetector:
    """
    Detector combinado:
    - z-score sobre janela deslizante de valores por chave (ex: latência, cpu, metric)
    - taxa de requisições (req/s) por chave
    """

    def __init__(
        self,
        window: int = 100,
        z_threshold: float = 3.0,
        rate_threshold: float = 60.0,
        rate_window_sec: float = 60.0,
    ):
        self.window = window
        self.z_threshold = z_threshold
        self.rate_threshold = rate_threshold
        self.rate_window_sec = rate_window_sec
        self._values: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=window)
        )
        self._timestamps: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=1000)
        )

    # --- valores (z-score) ---
    def observe(self, key: str, value: float, ts: Optional[float] = None) -> None:
        self._values[key].append(float(value))
        self._timestamps[key].append(ts if ts is not None else time.time())

    def stats(self, key: str) -> Dict[str, float]:
        vals = list(self._values[key])
        if not vals:
            return {"count": 0, "mean": 0.0, "std": 0.0}
        n = len(vals)
        mean = sum(vals) / n
        var = sum((x - mean) ** 2 for x in vals) / n if n > 1 else 0.0
        std = math.sqrt(var)
        return {
            "count": float(n),
            "mean": mean,
            "std": std,
            "min": min(vals),
            "max": max(vals),
        }

    def z_score(self, key: str, value: float) -> float:
        s = self.stats(key)
        if s["std"] == 0:
            return 0.0 if value == s["mean"] else 999.0
        return (value - s["mean"]) / s["std"]

    def is_anomaly(self, key: str, value: float) -> bool:
        """True se |z| > threshold e há amostras suficientes (>=10)."""
        if len(self._values[key]) < 10:
            return False
        return abs(self.z_score(key, value)) > self.z_threshold

    # --- taxa ---
    def rate(self, key: str, now: Optional[float] = None) -> float:
        """Req/s na janela rate_window_sec."""
        now = now if now is not None else time.time()
        q = self._timestamps[key]
        # conta eventos na janela
        cutoff = now - self.rate_window_sec
        cnt = sum(1 for t in q if t >= cutoff)
        return cnt / self.rate_window_sec if self.rate_window_sec else 0.0

    def is_rate_anomaly(self, key: str, now: Optional[float] = None) -> bool:
        return self.rate(key, now=now) > self.rate_threshold

    def check(
        self, key: str, value: float, now: Optional[float] = None
    ) -> Dict[str, object]:
        """Avaliação completa."""
        z = self.z_score(key, value)
        anom = self.is_anomaly(key, value)
        r = self.rate(key, now=now)
        rate_anom = self.is_rate_anomaly(key, now=now)
        return {
            "key": key,
            "value": value,
            "z_score": round(z, 3),
            "is_anomaly": anom,
            "rate_per_sec": round(r, 3),
            "is_rate_anomaly": rate_anom,
            "stats": self.stats(key),
        }

    def reset(self, key: Optional[str] = None) -> None:
        if key:
            self._values.pop(key, None)
            self._timestamps.pop(key, None)
        else:
            self._values.clear()
            self._timestamps.clear()


if __name__ == "__main__":
    det = AnomalyDetector(window=20, z_threshold=2.5, rate_threshold=5)
    for v in [10, 11, 9, 10, 10.5, 9.8, 10.2]:
        det.observe("cpu", v)
    print(det.stats("cpu"))
    print(det.check("cpu", 50))  # anomalia
    print(det.check("cpu", 10.1))  # normal
    # taxa
    now = time.time()
    for i in range(10):
        det.observe("api", 1, ts=now - i * 0.5)
    print(det.rate("api", now=now))
    print("anomaly OK")
