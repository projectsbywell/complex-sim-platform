"""
model_registry.py — registro de modelos (JSON) + métricas
Armazena em pipeline/registry.json (ou path via MODEL_REGISTRY_PATH).
Stdlib + numpy opcional. Sem dependências pesadas.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import numpy as np  # type: ignore
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

DEFAULT_PATH = Path(os.getenv("MODEL_REGISTRY_PATH") or Path(__file__).parent / "registry.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelRegistry:
    def __init__(self, path: Optional[str | Path] = None):
        self.path = Path(path or DEFAULT_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"models": []})

    def _read(self) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: Dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(self.path)

    def register(
        self,
        name: str,
        version: str = "0.1.0",
        framework: str = "sklearn",
        metrics: Optional[Dict[str, float]] = None,
        params: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        author: str = "system",
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "version": version,
            "framework": framework,
            "metrics": metrics or {},
            "params": params or {},
            "artifacts": artifacts or [],
            "tags": tags or [],
            "author": author,
            "created_at": _now(),
            "status": "registered",
        }
        data = self._read()
        data["models"].append(entry)
        self._write(data)
        return entry

    def list(self, name: Optional[str] = None, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        data = self._read()
        models = data.get("models", [])
        if name:
            models = [m for m in models if m["name"] == name]
        if tag:
            models = [m for m in models if tag in m.get("tags", [])]
        return sorted(models, key=lambda m: m["created_at"], reverse=True)

    def get(self, model_id: str) -> Optional[Dict[str, Any]]:
        for m in self._read().get("models", []):
            if m["id"] == model_id or m["name"] == model_id:
                return m
        return None

    def get_best(self, metric: str, higher_is_better: bool = False) -> Optional[Dict[str, Any]]:
        models = [m for m in self.list() if metric in m.get("metrics", {})]
        if not models:
            return None
        return sorted(models, key=lambda m: m["metrics"][metric], reverse=higher_is_better)[0]

    def update_metrics(self, model_id: str, metrics: Dict[str, float]) -> Dict[str, Any]:
        data = self._read()
        for m in data["models"]:
            if m["id"] == model_id:
                m["metrics"].update(metrics)
                m["updated_at"] = _now()
                self._write(data)
                return m
        raise KeyError(f"model {model_id} not found")

    def promote(self, model_id: str, stage: str = "production") -> Dict[str, Any]:
        assert stage in ("staging", "production", "archived", "registered")
        data = self._read()
        for m in data["models"]:
            if m["id"] == model_id:
                m["status"] = stage
                m["promoted_at"] = _now()
                self._write(data)
                return m
        raise KeyError(f"model {model_id} not found")

    def to_json(self) -> str:
        return json.dumps(self._read(), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    reg = ModelRegistry("/tmp/test_registry.json")
    a = reg.register("sir_predictor", version="1.0.0", metrics={"mae": 2.1, "r2": 0.92}, params={"lr": 0.01}, tags=["sir"])
    b = reg.register("sir_predictor", version="1.1.0", metrics={"mae": 1.8, "r2": 0.95}, params={"lr": 0.005}, tags=["sir"])
    print(reg.list())
    print("best mae:", reg.get_best("mae", higher_is_better=False))
    print("OK")
