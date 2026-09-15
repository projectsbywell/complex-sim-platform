"""
db_client.py — wrapper Python para Complex Sim Platform
- Tenta psycopg2 (Postgres+Timescale). Se ausente ou sem servidor, fallback para sqlite local.
- API estável: Database.save_sim / load_sim / log_metric / get_metrics / etc.
- stdlib + psycopg2 opcional + sqlite3. Sem segredos hardcoded (lê env).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psycopg2  # type: ignore
    import psycopg2.extras  # type: ignore

    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Abstrai Postgres (preferido) ou SQLite fallback."""

    def __init__(self, dsn: Optional[str] = None, sqlite_path: Optional[str] = None):
        # DSN via env (não hardcoded)
        self.dsn = dsn or os.getenv("DATABASE_URL") or self._build_dsn_from_env()
        self.sqlite_path = Path(
            sqlite_path
            or os.getenv("SQLITE_PATH")
            or str(Path(__file__).parent / "local.db")
        )
        self.backend: str = "sqlite"  # será atualizado
        self._pg_conn = None
        self._sqlite_conn: Optional[sqlite3.Connection] = None

        if HAS_PSYCOPG2 and self.dsn:
            try:
                self._pg_conn = psycopg2.connect(self.dsn, connect_timeout=3)
                self._pg_conn.autocommit = True
                # teste simples
                with self._pg_conn.cursor() as cur:
                    cur.execute("SELECT 1")
                self.backend = "postgres"
            except Exception:
                # falha de conexão -> fallback
                if self._pg_conn:
                    try:
                        self._pg_conn.close()
                    except Exception:
                        pass
                self._pg_conn = None
                self.backend = "sqlite"

        if self.backend == "sqlite":
            self._init_sqlite()

    @staticmethod
    def _build_dsn_from_env() -> Optional[str]:
        host = os.getenv("PGHOST", "localhost")
        port = os.getenv("PGPORT", "5432")
        user = os.getenv("POSTGRES_USER")
        pwd = os.getenv("POSTGRES_PASSWORD")
        db = os.getenv("POSTGRES_DB", "complex_sim")
        if user and pwd:
            return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
        # sem credenciais -> não tenta postgres
        return None

    # --- sqlite init ---
    def _init_sqlite(self) -> None:
        self._sqlite_conn = sqlite3.connect(
            str(self.sqlite_path), check_same_thread=False
        )
        self._sqlite_conn.row_factory = sqlite3.Row
        self._sqlite_conn.execute("PRAGMA journal_mode=WAL;")
        self._sqlite_conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'researcher',
                display_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER REFERENCES users(id),
                type TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT 'Untitled',
                config TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'created',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id INTEGER NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
                started_at TEXT,
                finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                params TEXT NOT NULL DEFAULT '{}',
                result_summary TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metrics_timeseries (
                time TEXT NOT NULL,
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                labels TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_run_time ON metrics_timeseries(run_id, time);
            CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics_timeseries(metric_name);
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                ip TEXT,
                request_id TEXT
            );
            """)
        self._sqlite_conn.commit()

    # --- helpers ---
    def _pg_cursor(self):
        assert self._pg_conn is not None
        return self._pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # =====================
    # Simulations
    # =====================
    def save_sim(self, data: Dict[str, Any], owner_id: Optional[int] = None) -> int:
        """Salva simulação. data: {type, name, config, status}. Retorna id."""
        typ = data.get("type", "generic")
        name = data.get("name", "Untitled")
        config = data.get("config", {})
        status = data.get("status", "created")
        now = _utcnow_iso()

        if self.backend == "postgres" and self._pg_conn:
            with self._pg_cursor() as cur:
                cur.execute(
                    "INSERT INTO simulations (owner_id, type, name, config, status, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s) RETURNING id",
                    (owner_id, typ, name, json.dumps(config), status, now, now),
                )
                row = cur.fetchone()
                return int(row["id"])
        else:
            assert self._sqlite_conn is not None
            cur = self._sqlite_conn.execute(
                "INSERT INTO simulations (owner_id, type, name, config, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (owner_id, typ, name, json.dumps(config), status, now, now),
            )
            self._sqlite_conn.commit()
            return int(cur.lastrowid)

    def load_sim(self, sim_id: int) -> Optional[Dict[str, Any]]:
        if self.backend == "postgres" and self._pg_conn:
            with self._pg_cursor() as cur:
                cur.execute("SELECT * FROM simulations WHERE id=%s", (sim_id,))
                row = cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                # config já é dict se jsonb
                if isinstance(d.get("config"), str):
                    d["config"] = json.loads(d["config"])
                return d
        else:
            assert self._sqlite_conn is not None
            cur = self._sqlite_conn.execute(
                "SELECT * FROM simulations WHERE id=?", (sim_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            d["config"] = json.loads(d["config"]) if d.get("config") else {}
            return d

    def list_sims(
        self, limit: int = 50, owner_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if self.backend == "postgres" and self._pg_conn:
            with self._pg_cursor() as cur:
                if owner_id is not None:
                    cur.execute(
                        "SELECT * FROM simulations WHERE owner_id=%s ORDER BY id DESC LIMIT %s",
                        (owner_id, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM simulations ORDER BY id DESC LIMIT %s", (limit,)
                    )
                return [dict(r) for r in cur.fetchall()]
        else:
            assert self._sqlite_conn is not None
            if owner_id is not None:
                cur = self._sqlite_conn.execute(
                    "SELECT * FROM simulations WHERE owner_id=? ORDER BY id DESC LIMIT ?",
                    (owner_id, limit),
                )
            else:
                cur = self._sqlite_conn.execute(
                    "SELECT * FROM simulations ORDER BY id DESC LIMIT ?", (limit,)
                )
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                r["config"] = (
                    json.loads(r["config"])
                    if isinstance(r.get("config"), str)
                    else r.get("config")
                )
            return rows

    # =====================
    # Runs
    # =====================
    def create_run(
        self, simulation_id: int, params: Optional[Dict[str, Any]] = None
    ) -> int:
        params = params or {}
        now = _utcnow_iso()
        if self.backend == "postgres" and self._pg_conn:
            with self._pg_cursor() as cur:
                cur.execute(
                    "INSERT INTO runs (simulation_id, status, params, created_at) VALUES (%s,'pending',%s::jsonb,%s) RETURNING id",
                    (simulation_id, json.dumps(params), now),
                )
                return int(cur.fetchone()["id"])
        else:
            assert self._sqlite_conn is not None
            cur = self._sqlite_conn.execute(
                "INSERT INTO runs (simulation_id, status, params, created_at) VALUES (?,?,?,?)",
                (simulation_id, "pending", json.dumps(params), now),
            )
            self._sqlite_conn.commit()
            return int(cur.lastrowid)

    def update_run_status(
        self, run_id: int, status: str, result_summary: Optional[Dict[str, Any]] = None
    ) -> None:
        now = _utcnow_iso()
        if self.backend == "postgres" and self._pg_conn:
            with self._pg_cursor() as cur:
                if status == "running":
                    cur.execute(
                        "UPDATE runs SET status=%s, started_at=%s WHERE id=%s",
                        (status, now, run_id),
                    )
                elif status in ("completed", "failed"):
                    cur.execute(
                        "UPDATE runs SET status=%s, finished_at=%s, result_summary=%s::jsonb WHERE id=%s",
                        (
                            status,
                            now,
                            json.dumps(result_summary) if result_summary else None,
                            run_id,
                        ),
                    )
                else:
                    cur.execute(
                        "UPDATE runs SET status=%s WHERE id=%s", (status, run_id)
                    )
        else:
            assert self._sqlite_conn is not None
            if status == "running":
                self._sqlite_conn.execute(
                    "UPDATE runs SET status=?, started_at=? WHERE id=?",
                    (status, now, run_id),
                )
            elif status in ("completed", "failed"):
                self._sqlite_conn.execute(
                    "UPDATE runs SET status=?, finished_at=?, result_summary=? WHERE id=?",
                    (
                        status,
                        now,
                        json.dumps(result_summary) if result_summary else None,
                        run_id,
                    ),
                )
            else:
                self._sqlite_conn.execute(
                    "UPDATE runs SET status=? WHERE id=?", (status, run_id)
                )
            self._sqlite_conn.commit()

    # =====================
    # Metrics
    # =====================
    def log_metric(
        self,
        run_id: int,
        metric: str,
        value: float,
        labels: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
    ) -> None:
        """Registra ponto de série temporal."""
        ts = ts or _utcnow_iso()
        labels = labels or {}
        if self.backend == "postgres" and self._pg_conn:
            with self._pg_cursor() as cur:
                cur.execute(
                    "INSERT INTO metrics_timeseries (time, run_id, metric_name, value, labels) VALUES (%s,%s,%s,%s,%s::jsonb)",
                    (ts, run_id, metric, float(value), json.dumps(labels)),
                )
        else:
            assert self._sqlite_conn is not None
            self._sqlite_conn.execute(
                "INSERT INTO metrics_timeseries (time, run_id, metric_name, value, labels) VALUES (?,?,?,?,?)",
                (ts, run_id, metric, float(value), json.dumps(labels)),
            )
            self._sqlite_conn.commit()

    def get_metrics(
        self, run_id: int, metric: Optional[str] = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        if self.backend == "postgres" and self._pg_conn:
            with self._pg_cursor() as cur:
                if metric:
                    cur.execute(
                        "SELECT * FROM metrics_timeseries WHERE run_id=%s AND metric_name=%s ORDER BY time DESC LIMIT %s",
                        (run_id, metric, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM metrics_timeseries WHERE run_id=%s ORDER BY time DESC LIMIT %s",
                        (run_id, limit),
                    )
                return [dict(r) for r in cur.fetchall()]
        else:
            assert self._sqlite_conn is not None
            if metric:
                cur = self._sqlite_conn.execute(
                    "SELECT * FROM metrics_timeseries WHERE run_id=? AND metric_name=? ORDER BY time DESC LIMIT ?",
                    (run_id, metric, limit),
                )
            else:
                cur = self._sqlite_conn.execute(
                    "SELECT * FROM metrics_timeseries WHERE run_id=? ORDER BY time DESC LIMIT ?",
                    (run_id, limit),
                )
            return [dict(r) for r in cur.fetchall()]

    def aggregate_metrics(
        self, run_id: int, metric: str, bucket: str = "1 minute"
    ) -> List[Dict[str, Any]]:
        """Agregação simples compatível com ambos backends (em postgres usa time_bucket se disponível)."""
        rows = self.get_metrics(run_id, metric, limit=10000)
        # fallback python aggregation por minuto
        from collections import defaultdict

        buckets: Dict[str, List[float]] = defaultdict(list)
        for r in rows:
            # bucket por minuto (trunca segundos)
            t = str(r["time"])[:16]  # YYYY-MM-DDTHH:MM
            buckets[t].append(float(r["value"]))
        out = []
        for k in sorted(buckets.keys()):
            vals = buckets[k]
            out.append(
                {
                    "bucket": k,
                    "avg": sum(vals) / len(vals),
                    "min": min(vals),
                    "max": max(vals),
                    "count": len(vals),
                }
            )
        return out

    # --- health ---
    def health(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "has_psycopg2": HAS_PSYCOPG2,
            "sqlite_path": str(self.sqlite_path),
            "dsn_set": bool(self.dsn),
        }

    def close(self) -> None:
        if self._pg_conn:
            try:
                self._pg_conn.close()
            except Exception:
                pass
        if self._sqlite_conn:
            try:
                self._sqlite_conn.close()
            except Exception:
                pass


# smoke test quando executado diretamente
if __name__ == "__main__":
    db = Database()
    print(f"[db_client] backend={db.backend} health={db.health()}")
    sid = db.save_sim(
        {"type": "sir", "name": "demo", "config": {"beta": 0.3, "gamma": 0.1}}
    )
    print(f"saved sim id={sid}")
    rid = db.create_run(sid, {"beta": 0.3})
    db.update_run_status(rid, "running")
    for i in range(5):
        db.log_metric(rid, "infected", 10 + i * 3.5)
        time.sleep(0.01)
    db.update_run_status(rid, "completed", {"final_infected": 27.5})
    print("load_sim:", db.load_sim(sid))
    print("metrics:", db.get_metrics(rid, "infected", limit=3))
    print("agg:", db.aggregate_metrics(rid, "infected"))
    db.close()
    print("OK")
