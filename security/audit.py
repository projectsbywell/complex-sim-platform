"""
audit.py — AuditLogger JSON lines
Campos: actor, action, resource, timestamp (ISO8601), details, ip, request_id
Saída: arquivo JSON lines + opcional stdout. Seguro para concorrência básica (append).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class AuditLogger:
    def __init__(self, path: Optional[str] = None, also_stdout: bool = False):
        self.path = Path(path or os.getenv("AUDIT_LOG_PATH") or "audit.log")
        self.also_stdout = also_stdout
        # garante diretório
        if self.path.parent and str(self.path.parent) != ".":
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        actor: str,
        action: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        ip: Optional[str] = None,
        request_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "actor": actor,
            "action": action,
            "resource": resource,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "details": details or {},
            "ip": ip,
            "request_id": request_id or uuid.uuid4().hex[:16],
        }
        line = json.dumps(entry, ensure_ascii=False)
        # append atômico (linha única)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.also_stdout:
            print(line)
        return entry

    def read(self, limit: int = 100) -> list[Dict[str, Any]]:
        """Lê últimas `limit` linhas."""
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        out = []
        for ln in lines[-limit:]:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
        return out

    def filter(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        rows = self.read(limit=10000)
        res = []
        for r in rows:
            if actor and r.get("actor") != actor:
                continue
            if action and r.get("action") != action:
                continue
            if resource and r.get("resource") != resource:
                continue
            res.append(r)
        return res[-limit:]

    def rotate_if_large(self, max_bytes: int = 10 * 1024 * 1024) -> Optional[Path]:
        """Rotaciona se arquivo > max_bytes. Retorna novo path ou None."""
        if not self.path.exists():
            return None
        if self.path.stat().st_size > max_bytes:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            new = self.path.with_suffix(f".{ts}.log")
            self.path.rename(new)
            return new
        return None


if __name__ == "__main__":
    lg = AuditLogger("/tmp/test_audit.log")  # nosec B108 -- demo path only
    lg.log(
        actor="alice", action="create_sim", resource="sim:1", details={"type": "sir"}
    )
    lg.log(actor="bob", action="login", resource="auth", ip="127.0.0.1")
    print(lg.read())
    print("audit OK")
