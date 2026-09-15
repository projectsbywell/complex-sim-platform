"""Storage layer: pluggable backend interface + JSON-file persistence (default).

The active backend keeps collections in memory and mirrors them to
``DATA_DIR/users.json`` / ``DATA_DIR/simulations.json`` with atomic writes, so
the platform runs with zero external services. ``StorageBackend`` is the seam
where Postgres / Timescale / Mongo adapters plug in when ``DATABASE_URL`` is
set — no other module talks to persistence directly.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import settings

logger = logging.getLogger("complex_sim.store")


class StorageError(RuntimeError):
    """Base class for store failures."""


class DuplicateUserError(StorageError):
    """Raised when registering an existing username."""


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------


class StorageBackend:
    """Minimal document-store interface (collection -> key -> document).

    Implementations must be thread-safe. The JSON-file implementation below
    is the default; a Postgres/Timescale adapter would map ``collection`` to a
    table and ``Mongo adapter`` to a collection in the MongoDB database named
    by ``DATABASE_URL``.
    """

    def get(self, collection: str, key: str) -> Optional[dict]:
        raise NotImplementedError

    def put(self, collection: str, key: str, doc: dict) -> None:
        raise NotImplementedError

    def delete(self, collection: str, key: str) -> bool:
        raise NotImplementedError

    def all(self, collection: str) -> "dict[str, dict]":
        raise NotImplementedError

    def flush(self) -> None:
        raise NotImplementedError


class JsonFileBackend(StorageBackend):
    """In-memory dicts mirrored to JSON files with atomic writes."""

    COLLECTIONS = ("users", "simulations")

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._collections: dict[str, dict[str, dict]] = {}
        self._lock = threading.RLock()
        for collection in self.COLLECTIONS:
            path = self.data_dir / f"{collection}.json"
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    docs = raw.get(collection, raw) if isinstance(raw, dict) else raw
                    self._collections[collection] = (
                        {str(k): v for k, v in docs.items()}
                        if isinstance(docs, dict)
                        else {}
                    )
                    logger.info(
                        "loaded %d %s from %s",
                        len(self._collections[collection]),
                        collection,
                        path,
                    )
                except Exception as exc:  # corrupt file: quarantine and reset
                    backup = path.with_suffix(f".corrupt-{int(time.time())}.json")
                    try:
                        path.rename(backup)
                    except OSError:
                        backup = None
                    self._collections[collection] = {}
                    logger.error(
                        "corrupt %s (%s); started empty%s",
                        path,
                        exc,
                        f"; quarantined to {backup}" if backup else "",
                    )
            else:
                self._collections[collection] = {}

    def get(self, collection: str, key: str) -> Optional[dict]:
        with self._lock:
            doc = self._collections.get(collection, {}).get(key)
            return dict(doc) if doc is not None else None

    def put(self, collection: str, key: str, doc: dict) -> None:
        with self._lock:
            self._collections.setdefault(collection, {})[key] = doc
            self._save(collection)

    def delete(self, collection: str, key: str) -> bool:
        with self._lock:
            coll = self._collections.get(collection)
            if coll is None or key not in coll:
                return False
            del coll[key]
            self._save(collection)
            return True

    def all(self, collection: str) -> "dict[str, dict]":
        with self._lock:
            return {
                k: dict(v) for k, v in self._collections.get(collection, {}).items()
            }

    def flush(self) -> None:
        with self._lock:
            for collection in self.COLLECTIONS:
                self._save(collection)

    def _save(self, collection: str) -> None:
        path = self.data_dir / f"{collection}.json"
        fd, tmp = tempfile.mkstemp(
            dir=self.data_dir, prefix=f".{collection}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(
                    {collection: self._collections.get(collection, {})},
                    fh,
                    ensure_ascii=False,
                    default=str,
                )
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def build_backend() -> StorageBackend:
    """Return the active storage backend.

    With ``DATABASE_URL`` set, logs that the external-storage interface is
    ready (drivers plug in behind ``StorageBackend``) and keeps the durable
    JSON backend active so the platform never loses data in this build.
    """
    url = settings.database_url
    if url:
        scheme = url.split(":", 1)[0].lower()
        logger.warning(
            "DATABASE_URL set (%s://...) — external storage interface ready; "
            "no driver compiled in this build, using JSON backend under %s",
            scheme,
            settings.data_dir,
        )
    return JsonFileBackend(settings.data_dir)


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass
class User:
    username: str
    hashed_password: str
    role: str = "user"  # "user" | "admin"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Simulation:
    id: str
    kind: str
    params: dict[str, Any]
    state: dict[str, Any]
    owner: str
    steps_done: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, include_state: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "params": self.params,
            "owner": self.owner,
            "steps_done": self.steps_done,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_state:
            payload["state"] = self.state
        return payload


# ---------------------------------------------------------------------------
# Store facade (thread-safe)
# ---------------------------------------------------------------------------


class Store:
    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend
        self._lock = threading.RLock()
        self.users: dict[str, User] = {}
        self.simulations: dict[str, Simulation] = {}
        self._load()

    # -- bootstrap ----------------------------------------------------------
    def _load(self) -> None:
        for name, doc in self._backend.all("users").items():
            self.users[str(name)] = User(
                username=str(doc.get("username", name)),
                hashed_password=str(doc.get("hashed_password", "")),
                role=str(doc.get("role", "user")),
                created_at=float(doc.get("created_at", 0.0)),
            )
        for sim_id, doc in self._backend.all("simulations").items():
            self.simulations[str(sim_id)] = Simulation(
                id=str(sim_id),
                kind=str(doc.get("kind", "")),
                params=dict(doc.get("params") or {}),
                state=dict(doc.get("state") or {}),
                owner=str(doc.get("owner", "")),
                steps_done=int(doc.get("steps_done", 0)),
                created_at=float(doc.get("created_at", 0.0)),
                updated_at=float(doc.get("updated_at", 0.0)),
            )

    # -- users ---------------------------------------------------------------
    def create_user(
        self, username: str, hashed_password: str, role: str = "user"
    ) -> User:
        with self._lock:
            if username in self.users:
                raise DuplicateUserError(f"username already taken: {username}")
            user = User(username=username, hashed_password=hashed_password, role=role)
            self.users[username] = user
            self._backend.put("users", username, user.to_dict())
            return user

    def get_user(self, username: str) -> Optional[User]:
        with self._lock:
            return self.users.get(username)

    def count_users(self) -> int:
        with self._lock:
            return len(self.users)

    # -- simulations ----------------------------------------------------------
    def create_simulation(
        self, kind: str, params: dict[str, Any], owner: str
    ) -> Simulation:
        with self._lock:
            now = time.time()
            sim = Simulation(
                id=uuid.uuid4().hex,
                kind=kind,
                params=params,
                state={},
                owner=owner,
                created_at=now,
                updated_at=now,
            )
            self.simulations[sim.id] = sim
            self._backend.put("simulations", sim.id, sim.to_dict())
            return sim

    def get_simulation(self, sim_id: str) -> Optional[Simulation]:
        with self._lock:
            return self.simulations.get(sim_id)

    def list_simulations(self, owner: Optional[str] = None) -> list[Simulation]:
        with self._lock:
            if owner is None:
                return list(self.simulations.values())
            return [s for s in self.simulations.values() if s.owner == owner]

    def save_simulation(self, sim: Simulation) -> None:
        with self._lock:
            self.simulations[sim.id] = sim
            self._backend.put("simulations", sim.id, sim.to_dict())

    def delete_simulation(self, sim_id: str) -> bool:
        with self._lock:
            if sim_id not in self.simulations:
                return False
            del self.simulations[sim_id]
            return self._backend.delete("simulations", sim_id)

    def count_simulations(self) -> int:
        with self._lock:
            return len(self.simulations)


store = Store(build_backend())
