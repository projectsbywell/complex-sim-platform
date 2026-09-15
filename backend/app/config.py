"""Central runtime configuration, read from environment variables.

Every tunable is env-driven so the same codebase runs in dev, Docker and
production. Values mirror ``.env.example``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    try:
        return int(v.strip())
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    try:
        return float(v.strip())
    except ValueError:
        return default


def _env_list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return tuple(item.strip() for item in v.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Application settings (frozen; read once at import time)."""

    app_name: str = "complex-sim-platform API"
    version: str = "1.0.0"
    description: str = (
        "Backend API for the complex simulation platform: multi-kind simulation "
        "engine (particles, fluids, physics, neural, bio) with JWT auth, "
        "real-time WebSocket stepping, export and reporting."
    )

    # --- auth -------------------------------------------------------------
    secret_key: str = os.getenv("SECRET_KEY", "dev-insecure-secret-change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    admin_users: tuple[str, ...] = _env_list("ADMIN_USERS", ("admin",))

    # --- storage ----------------------------------------------------------
    # Empty DATABASE_URL -> in-memory + JSON files under DATA_DIR.
    # When set, the storage layer is ready for Postgres / Timescale / Mongo
    # (see app/store.py StorageBackend interface).
    database_url: str = os.getenv("DATABASE_URL", "")
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DATA_DIR", "./data"))
    )

    # --- rate limiting ----------------------------------------------------
    rate_limit_per_minute: int = _env_int("RATE_LIMIT_PER_MINUTE", 100)
    rate_limit_exempt: tuple[str, ...] = _env_list(
        "RATE_LIMIT_EXEMPT", ("/health", "/docs", "/redoc", "/openapi.json")
    )
    ws_message_limit_per_minute: int = _env_int("WS_MESSAGE_LIMIT_PER_MINUTE", 120)

    # --- cache -------------------------------------------------------------
    cache_ttl_seconds: int = _env_int("CACHE_TTL_SECONDS", 60)
    cache_maxsize: int = _env_int("CACHE_MAXSIZE", 1024)

    # --- simulation engine -------------------------------------------------
    sim_core_path: str = os.getenv("SIM_CORE_PATH", "../simulation-core")
    sim_max_work: int = _env_int("SIM_MAX_WORK", 20_000_000)

    # --- misc ---------------------------------------------------------------
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    cors_origins: tuple[str, ...] = _env_list("CORS_ORIGINS", ("*",))

    def storage_backend(self) -> str:
        """Human-readable name of the active storage backend."""
        if not self.database_url:
            return "json"
        scheme = self.database_url.split(":", 1)[0].lower()
        if scheme.startswith("postgres"):
            return "postgres"
        if scheme in {"timescale", "timescaledb"}:
            return "timescale"
        if scheme == "mongodb":
            return "mongo"
        return "external"


settings = Settings()
