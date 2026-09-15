"""Simulation engine service.

Loads the real ``simcore`` package from ``SIM_CORE_PATH`` (resolved relative
to the backend directory) when it imports cleanly, and falls back to the
built-in lightweight mock engines below otherwise — startup never crashes.

Engine instances live in memory keyed by simulation id; their serialisable
state is persisted through the store after every mutation. All five kinds
(particles, fluids, physics, neural, bio) implement the same
``Simulatable``-style interface as the real simcore: ``step(dt)``,
``get_state()``, ``set_state(d)``, ``get_params()``, ``set_params(p)``.
"""

from __future__ import annotations

import io
import json
import logging
import math
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .cache import cache
from .config import settings
from .store import Simulation, store

logger = logging.getLogger("complex_sim.sim")

SIM_KINDS = ["particles", "fluids", "physics", "neural", "bio"]
ALLOWED_KINDS = frozenset(SIM_KINDS)

EXPORT_MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "parquet": "application/vnd.apache.parquet",
    "hdf5": "application/x-hdf5",
}


class ExportUnavailableError(RuntimeError):
    """Raised when the exporter library for a format is not installed."""


class WorkLimitError(RuntimeError):
    """Raised when a step request exceeds the configured work budget."""


# ---------------------------------------------------------------------------
# simcore loader
# ---------------------------------------------------------------------------


class SimCoreInfo:
    def __init__(self, module: Any, mode: str, version: str) -> None:
        self.module = module
        self.mode = mode  # "real" | "mock"
        self.version = version

    def to_dict(self) -> dict[str, str]:
        return {"mode": self.mode, "version": self.version}


def _load_simcore() -> SimCoreInfo:
    """Import the real simcore when possible; otherwise return mock info."""
    raw = settings.sim_core_path
    path = Path(raw)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parent.parent / raw).resolve()
    else:
        path = path.resolve()
    if not path.exists():
        logger.warning("simcore path %s not found — using built-in mock engines", path)
        return SimCoreInfo(None, "mock", "")
    sys.path.insert(0, str(path))
    try:
        import simcore  # noqa: F401

        if not (
            hasattr(simcore, "SimulationEngine") or hasattr(simcore, "Simulatable")
        ):
            raise RuntimeError("simcore does not expose SimulationEngine/Simulatable")
        version = str(getattr(simcore, "__version__", "unknown"))
        logger.info("simcore loaded: mode=real version=%s path=%s", version, path)
        return SimCoreInfo(simcore, "real", version)
    except Exception as exc:
        logger.warning("import simcore failed (%s) — using built-in mock engines", exc)
        return SimCoreInfo(None, "mock", str(exc)[:160])


def to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy/foreign types into plain JSON-safe Python."""
    if obj is None or isinstance(obj, (bool, str, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else 0.0
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return to_jsonable(item())
        except Exception:
            pass
    tolist = getattr(obj, "tolist", None)
    if callable(tolist):
        try:
            return to_jsonable(tolist())
        except Exception:
            pass
    return str(obj)


# ---------------------------------------------------------------------------
# Built-in mock engines (same interface as simcore.Simulatable)
# ---------------------------------------------------------------------------


class _BaseMockEngine:
    """Common machinery: params merge, clock, rolling history."""

    KIND = "base"
    DEFAULTS: dict[str, Any] = {}

    def __init__(self, params: Optional[dict] = None) -> None:
        self.params: dict[str, Any] = {**self.DEFAULTS, **(params or {})}
        self.t: float = 0.0
        self.history: list[dict[str, float]] = []
        self._init()

    # -- interface ---------------------------------------------------------
    def _init(self) -> None:
        pass

    def step(self, dt: float) -> None:
        raise NotImplementedError

    def get_state(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "kind": self.KIND,
            "history": self._history_tail(),
            **self._state_extra(),
        }

    def _state_extra(self) -> dict[str, Any]:
        raise NotImplementedError

    def set_state(self, d: dict) -> None:
        self.t = float(d.get("t", 0.0))
        raw = d.get("history")
        self.history = [dict(e) for e in raw] if isinstance(raw, list) else []
        self._restore(d)

    def _restore(self, d: dict) -> None:
        pass

    def get_params(self) -> dict[str, Any]:
        return dict(self.params)

    def set_params(self, p: dict) -> None:
        self.params = {
            **self.params,
            **{k: v for k, v in p.items() if k in self.DEFAULTS},
        }

    # -- helpers ------------------------------------------------------------
    def _record(self, **metrics: float) -> None:
        entry: dict[str, float] = {"t": round(self.t, 6)}
        for key, value in metrics.items():
            try:
                entry[key] = round(float(value), 6)
            except (TypeError, ValueError):
                entry[key] = 0.0
        self.history.append(entry)
        cap = max(1, int(self.params.get("record_length", 200)))
        if len(self.history) > cap:
            self.history = self.history[-cap:]

    def _history_tail(self) -> list[dict[str, float]]:
        return list(self.history)

    def work_estimate(self) -> int:
        return 1

    @classmethod
    def merge_defaults(cls, params: Optional[dict]) -> dict[str, Any]:
        merged = {**cls.DEFAULTS, **(params or {})}
        merged["record_length"] = max(
            10, min(5000, int(merged.get("record_length", 200)))
        )
        return merged


class ParticlesEngine(_BaseMockEngine):
    """Billiard-style particles bouncing inside a unit square."""

    KIND = "particles"
    DEFAULTS = {"n": 64, "seed": 42, "speed": 0.08, "record_length": 200}

    def _init(self) -> None:
        rng = random.Random(int(self.params.get("seed", 42)))
        n = max(2, min(4096, int(self.params.get("n", 64))))
        self.params["n"] = n
        speed = abs(float(self.params.get("speed", 0.08)))
        self.positions = [[rng.random(), rng.random()] for _ in range(n)]
        self.velocities = [
            [(rng.random() - 0.5) * 2.0 * speed, (rng.random() - 0.5) * 2.0 * speed]
            for _ in range(n)
        ]

    def step(self, dt: float) -> None:
        for p, v in zip(self.positions, self.velocities):
            p[0] += v[0] * dt
            p[1] += v[1] * dt
            if p[0] <= 0.0:
                p[0], v[0] = -p[0], abs(v[0])
            elif p[0] >= 1.0:
                p[0], v[0] = 2.0 - p[0], -abs(v[0])
            if p[1] <= 0.0:
                p[1], v[1] = -p[1], abs(v[1])
            elif p[1] >= 1.0:
                p[1], v[1] = 2.0 - p[1], -abs(v[1])
        self.t += dt
        ke = 0.5 * sum(v[0] * v[0] + v[1] * v[1] for v in self.velocities)
        mean_speed = sum(math.hypot(v[0], v[1]) for v in self.velocities) / len(
            self.velocities
        )
        self._record(kinetic_energy=ke, mean_speed=mean_speed)

    def _state_extra(self) -> dict[str, Any]:
        ke = 0.5 * sum(v[0] * v[0] + v[1] * v[1] for v in self.velocities)
        return {
            "positions": self.positions,
            "velocities": self.velocities,
            "kinetic_energy": ke,
        }

    def _restore(self, d: dict) -> None:
        try:
            self.positions = [[float(x), float(y)] for x, y in d.get("positions", [])]
            self.velocities = [[float(x), float(y)] for x, y in d.get("velocities", [])]
        except (TypeError, ValueError):
            self._init()

    def work_estimate(self) -> int:
        return int(self.params.get("n", 64))


class FluidsEngine(_BaseMockEngine):
    """Scalar-field diffusion on a grid with injected sources."""

    KIND = "fluids"
    DEFAULTS = {
        "width": 32,
        "height": 32,
        "diffusion": 0.08,
        "sources": 3,
        "seed": 7,
        "record_length": 200,
    }

    def _init(self) -> None:
        w = max(8, min(128, int(self.params.get("width", 32))))
        h = max(8, min(128, int(self.params.get("height", 32))))
        self.params["width"] = w
        self.params["height"] = h
        self.field = [[0.0] * w for _ in range(h)]
        rng = random.Random(int(self.params.get("seed", 7)))
        for _ in range(max(1, min(16, int(self.params.get("sources", 3))))):
            ci, cj = rng.randrange(h), rng.randrange(w)
            for i in range(max(0, ci - 2), min(h, ci + 3)):
                for j in range(max(0, cj - 2), min(w, cj + 3)):
                    self.field[i][j] = min(1.0, self.field[i][j] + 0.25)

    def step(self, dt: float) -> None:
        h, w = int(self.params["height"]), int(self.params["width"])
        d = abs(float(self.params.get("diffusion", 0.08))) * dt
        f = self.field
        new = [row[:] for row in f]
        for i in range(1, h - 1):
            for j in range(1, w - 1):
                lap = (
                    f[i - 1][j]
                    + f[i + 1][j]
                    + f[i][j - 1]
                    + f[i][j + 1]
                    - 4.0 * f[i][j]
                )
                new[i][j] += lap * d
        self.field = [[min(1.0, max(0.0, v)) for v in row] for row in new]
        self.t += dt
        mass = sum(sum(row) for row in self.field)
        mx = max(max(row) for row in self.field)
        self._record(total_mass=mass, max_density=mx)

    def _state_extra(self) -> dict[str, Any]:
        mass = sum(sum(row) for row in self.field)
        mx = max(max(row) for row in self.field)
        return {
            "width": self.params["width"],
            "height": self.params["height"],
            "field": self.field,
            "total_mass": mass,
            "max_density": mx,
        }

    def _restore(self, d: dict) -> None:
        try:
            self.field = [[float(v) for v in row] for row in d.get("field", [])]
        except (TypeError, ValueError):
            self._init()

    def work_estimate(self) -> int:
        return int(self.params.get("width", 32)) * int(self.params.get("height", 32))


class PhysicsEngine(_BaseMockEngine):
    """Damped pendulum (theta/omega with total mechanical energy)."""

    KIND = "physics"
    DEFAULTS = {
        "gravity": 9.81,
        "length": 1.0,
        "damping": 0.1,
        "theta0": 1.5,
        "omega0": 0.0,
        "record_length": 200,
    }

    def _init(self) -> None:
        self.theta = float(self.params.get("theta0", 1.5))
        self.omega = float(self.params.get("omega0", 0.0))

    def step(self, dt: float) -> None:
        g = abs(float(self.params.get("gravity", 9.81)))
        length = max(1e-6, abs(float(self.params.get("length", 1.0))))
        damping = abs(float(self.params.get("damping", 0.1)))
        self.omega += (-(g / length) * math.sin(self.theta) - damping * self.omega) * dt
        self.theta += self.omega * dt
        self.t += dt
        energy = 0.5 * length * length * self.omega * self.omega + g * length * (
            1.0 - math.cos(self.theta)
        )
        self._record(theta=self.theta, omega=self.omega, energy=energy)

    def _state_extra(self) -> dict[str, float]:
        g = abs(float(self.params.get("gravity", 9.81)))
        length = max(1e-6, abs(float(self.params.get("length", 1.0))))
        energy = 0.5 * length * length * self.omega * self.omega + g * length * (
            1.0 - math.cos(self.theta)
        )
        return {"theta": self.theta, "omega": self.omega, "energy": energy}

    def _restore(self, d: dict) -> None:
        try:
            self.theta = float(d.get("theta", 1.5))
            self.omega = float(d.get("omega", 0.0))
        except (TypeError, ValueError):
            self._init()


class NeuralEngine(_BaseMockEngine):
    """Rate-coded recurrent network with sigmoid activation."""

    KIND = "neural"
    DEFAULTS = {
        "n": 16,
        "tau": 10.0,
        "input": 0.5,
        "coupling": 0.6,
        "seed": 3,
        "record_length": 200,
    }

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    def _init(self) -> None:
        n = max(2, min(256, int(self.params.get("n", 16))))
        self.params["n"] = n
        rng = random.Random(int(self.params.get("seed", 3)))
        coupling = abs(float(self.params.get("coupling", 0.6)))
        self.weights = [
            [(rng.random() - 0.5) * 2.0 * coupling for _ in range(n)] for _ in range(n)
        ]
        self.rates = [rng.random() * 0.5 for _ in range(n)]

    def step(self, dt: float) -> None:
        n = int(self.params["n"])
        tau = max(1e-3, abs(float(self.params.get("tau", 10.0))))
        inp = float(self.params.get("input", 0.5))
        rates = self.rates
        new_rates = []
        for i in range(n):
            drive = sum(self.weights[i][j] * self._sigmoid(rates[j]) for j in range(n))
            r = rates[i] + (-rates[i] / tau + drive + inp) * dt
            new_rates.append(max(0.0, min(5.0, r)))
        self.rates = new_rates
        self.t += dt
        acts = [self._sigmoid(r) for r in self.rates]
        self._record(
            mean_rate=sum(self.rates) / n,
            mean_activity=sum(acts) / n,
            spikes=sum(1.0 for a in acts if a > 0.5),
        )

    def _state_extra(self) -> dict[str, Any]:
        n = int(self.params["n"])
        acts = [self._sigmoid(r) for r in self.rates]
        return {
            "n": n,
            "rates": self.rates,
            "weights": self.weights,
            "mean_rate": sum(self.rates) / n,
            "mean_activity": sum(acts) / n,
        }

    def _restore(self, d: dict) -> None:
        try:
            self.rates = [float(v) for v in d.get("rates", [])]
            weights = d.get("weights")
            if weights:
                self.weights = [[float(v) for v in row] for row in weights]
        except (TypeError, ValueError):
            self._init()

    def work_estimate(self) -> int:
        n = int(self.params.get("n", 16))
        return n * n


class BioEngine(_BaseMockEngine):
    """Lotka-Volterra predator/prey populations."""

    KIND = "bio"
    DEFAULTS = {
        "prey0": 40.0,
        "predator0": 9.0,
        "alpha": 0.1,
        "beta": 0.02,
        "gamma": 0.1,
        "delta": 0.01,
        "record_length": 200,
    }

    def _init(self) -> None:
        self.prey = float(self.params.get("prey0", 40.0))
        self.predators = float(self.params.get("predator0", 9.0))

    def step(self, dt: float) -> None:
        alpha = abs(float(self.params.get("alpha", 0.1)))
        beta = abs(float(self.params.get("beta", 0.02)))
        gamma = abs(float(self.params.get("gamma", 0.1)))
        delta = abs(float(self.params.get("delta", 0.01)))
        prey, pred = self.prey, self.predators
        dprey = (alpha * prey - beta * prey * pred) * dt
        dpred = (-gamma * pred + delta * prey * pred) * dt
        self.prey = max(0.0, prey + dprey)
        self.predators = max(0.0, pred + dpred)
        self.t += dt
        self._record(prey=self.prey, predators=self.predators)

    def _state_extra(self) -> dict[str, float]:
        return {
            "prey": self.prey,
            "predators": self.predators,
            "ratio": self.predators / max(1e-9, self.prey),
        }

    def _restore(self, d: dict) -> None:
        try:
            self.prey = float(d.get("prey", 40.0))
            self.predators = float(d.get("predators", 9.0))
        except (TypeError, ValueError):
            self._init()


_MOCK_ENGINES: dict[str, type] = {
    cls.KIND: cls
    for cls in (ParticlesEngine, FluidsEngine, PhysicsEngine, NeuralEngine, BioEngine)
}


# ---------------------------------------------------------------------------
# Adapter for the real simcore engines
# ---------------------------------------------------------------------------


def _sample_metrics(state: dict) -> dict[str, float]:
    """Derive scalar traces from any state dict (for chart histories)."""
    out: dict[str, float] = {}
    for key, value in state.items():
        if (
            key in ("history", "step", "loss_history", "arch")
            or isinstance(value, (str, bool))
            or value is None
        ):
            continue
        if isinstance(value, (int, float)):
            out[key] = float(value)
        elif isinstance(value, list):
            nums = _flatten_numbers(value)
            if nums:
                out[f"{key}_mean"] = sum(nums) / len(nums)
                out[f"{key}_max"] = max(nums)
        elif isinstance(value, dict):
            for sub, item in value.items():
                nums = _flatten_numbers(item)
                if nums:
                    out[f"{key}_{sub}"] = sum(nums) / len(nums)
    return out


class _RealEngineAdapter:
    """Uniform Simulatable-style wrapper over a real simcore engine.

    Tracks its own clock (``t``) and samples scalar metrics after every step
    so the report/export layer sees the same shape as the mock engines —
    ``{"t", "kind", "history", ...state}``.
    """

    _backend = "real"

    def __init__(self, real: Any, kind: str, params: dict) -> None:
        self._real = real
        self._kind = kind
        self.params = dict(params)
        self.t = 0.0
        self.history: list[dict[str, float]] = []

    def step(self, dt: float) -> None:
        self._real.step(dt)
        self.t += dt
        try:
            metrics = _sample_metrics(to_jsonable(self._real.get_state()))
        except Exception:
            metrics = {}
        entry = {
            "t": round(self.t, 6),
            **{k: round(float(v), 6) for k, v in metrics.items()},
        }
        self.history.append(entry)
        cap = max(1, int(self.params.get("record_length", 200)))
        if len(self.history) > cap:
            self.history = self.history[-cap:]

    def get_state(self) -> dict[str, Any]:
        state = to_jsonable(self._real.get_state())
        state["kind"] = self._kind
        state["t"] = self.t
        state["history"] = list(self.history)
        return state

    def set_state(self, d: dict) -> None:
        real_d = {k: v for k, v in d.items() if k not in ("t", "kind", "history")}
        try:
            self._real.set_state(real_d)
        except Exception as exc:
            logger.warning("simcore set_state failed on %s (%s)", self._kind, exc)
        self.t = float(d.get("t", 0.0))
        raw = d.get("history")
        self.history = [dict(e) for e in raw] if isinstance(raw, list) else []

    def get_params(self) -> dict[str, Any]:
        return dict(self.params)

    def set_params(self, p: dict) -> None:
        try:
            self._real.set_params(p)
        except Exception:
            pass
        self.params = {**self.params, **p}

    def work_estimate(self) -> int:
        n = (
            self.params.get("n")
            or self.params.get("width")
            or self.params.get("grid_size")
        )
        if n:
            n = int(n)
            return n * n
        return 1024

    @classmethod
    def merge_defaults(cls, params: Optional[dict]) -> dict[str, Any]:
        merged = dict(params or {})
        if "record_length" not in merged:
            merged["record_length"] = 200
        return merged


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SimulationService:
    def __init__(self) -> None:
        self._simcore = _load_simcore()
        self._engines: dict[str, Any] = {}
        self._engine_locks: dict[str, threading.Lock] = {}
        self._backends: dict[str, str] = {}
        self._lock = threading.RLock()

    # -- introspection ------------------------------------------------------
    def simcore_info(self) -> dict[str, str]:
        return self._simcore.to_dict()

    def kinds(self) -> list[str]:
        return list(SIM_KINDS)

    def engine_backend(self) -> str:
        return "simcore" if self._simcore.mode == "real" else "mock"

    # -- life-cycle ----------------------------------------------------------
    def _build_engine(
        self,
        kind: str,
        params: dict,
        state: Optional[dict] = None,
        prefer_real: bool = True,
    ) -> Any:
        """Build the best engine for a kind: real simcore first, mock fallback."""
        if prefer_real and self._simcore.module is not None:
            try:
                real = self._simcore.module.SimulationEngine(kind, params)
                real.step(1e-9)  # runtime sanity probe (negligible delta)
                adapter = _RealEngineAdapter(real, kind, params)
                if state:
                    adapter.set_state(state)
                return adapter
            except Exception as exc:
                logger.warning(
                    "simcore engine for kind %r failed (%s); using mock engine",
                    kind,
                    exc,
                )
        cls = _MOCK_ENGINES.get(kind)
        if cls is None:
            raise ValueError(f"unknown simulation kind {kind!r}; allowed: {SIM_KINDS}")
        merged = cls.merge_defaults(params)
        engine = cls(merged)
        if state:
            engine.set_state(state)
        return engine

    def create(self, kind: str, params: dict, owner: str) -> Simulation:
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"unknown simulation kind {kind!r}; allowed: {SIM_KINDS}")
        try:
            engine = self._build_engine(kind, params, prefer_real=True)
            backend = engine._backend
        except Exception:
            engine = self._build_engine(kind, params, prefer_real=False)
            backend = engine._backend
        sim = store.create_simulation(kind, params, owner)
        sim.state = to_jsonable(engine.get_state())
        store.save_simulation(sim)
        with self._lock:
            self._engines[sim.id] = engine
            self._backends[sim.id] = backend
        return sim

    def get(self, sim_id: str) -> Simulation:
        sim = store.get_simulation(sim_id)
        if sim is None:
            raise KeyError(sim_id)
        return sim

    def delete(self, sim_id: str) -> bool:
        with self._lock:
            self._engines.pop(sim_id, None)
            self._engine_locks.pop(sim_id, None)
            self._backends.pop(sim_id, None)
        cache.delete(f"sim:{sim_id}")
        return store.delete_simulation(sim_id)

    # -- stepping --------------------------------------------------------------
    def _engine_lock(self, sim_id: str) -> threading.Lock:
        with self._lock:
            lock = self._engine_locks.get(sim_id)
            if lock is None:
                lock = threading.Lock()
                self._engine_locks[sim_id] = lock
            return lock

    def _get_engine(self, sim: Simulation) -> Any:
        with self._lock:
            engine = self._engines.get(sim.id)
            if engine is not None:
                return engine
        engine = self._build_engine(sim.kind, sim.params, sim.state, prefer_real=True)
        with self._lock:
            self._engines[sim.id] = engine
            self._backends[sim.id] = engine._backend
        return engine

    def step(self, sim_id: str, dt: float, steps: int) -> tuple[dict, int, float]:
        """Advance a simulation; returns (state, total_steps_done, t)."""
        sim = self.get(sim_id)
        lock = self._engine_lock(sim_id)
        with lock:
            engine = self._get_engine(sim)
            budget = int(settings.sim_max_work)
            if steps * engine.work_estimate() > budget:
                raise WorkLimitError(
                    f"step request too heavy: {steps} steps on kind "
                    f"{sim.kind!r} exceeds work budget {budget}"
                )
            try:
                for _ in range(steps):
                    engine.step(dt)
            except Exception as exc:
                if getattr(engine, "_backend", "mock") == "real":
                    # real simcore engine broke at runtime: demote to mock
                    logger.error(
                        "real engine failed at runtime on %s (%s); demoting to mock",
                        sim_id,
                        exc,
                    )
                    engine = self._build_engine(
                        sim.kind, sim.params, sim.state, prefer_real=False
                    )
                    with self._lock:
                        self._engines[sim.id] = engine
                        self._backends[sim.id] = "mock"
                    for _ in range(steps):
                        engine.step(dt)
                else:
                    raise
            sim.state = to_jsonable(engine.get_state())
            sim.steps_done += steps
            sim.updated_at = time.time()
            store.save_simulation(sim)
        cache.delete(f"sim:{sim_id}")
        t = float(sim.state.get("t", 0.0))
        return sim.state, sim.steps_done, t

    # -- export ----------------------------------------------------------------
    def export_file(self, sim_id: str, fmt: str) -> tuple[str, str, bytes]:
        """Return (filename, media_type, payload) for the requested format."""
        sim = self.get(sim_id)
        state = sim.state
        if fmt == "json":
            body = json.dumps(
                {
                    "id": sim.id,
                    "kind": sim.kind,
                    "steps_done": sim.steps_done,
                    "params": sim.params,
                    "state": state,
                },
                indent=2,
                default=str,
            ).encode("utf-8")
            return f"sim_{sim.id}.json", EXPORT_MEDIA["json"], body

        if fmt == "csv":
            frame = self._state_frame(state)
            try:
                import pandas as pd

                df = pd.DataFrame({k: pd.Series(v) for k, v in frame.items()})
                body = df.to_csv(index=False).encode("utf-8")
            except ImportError:
                body = self._csv_stdlib(frame).encode("utf-8")
            return f"sim_{sim.id}.csv", EXPORT_MEDIA["csv"], body

        if fmt == "parquet":
            try:
                import pandas as pd
                import pyarrow  # noqa: F401
            except ImportError as exc:
                raise ExportUnavailableError(
                    "parquet export requires pandas + pyarrow"
                ) from exc
            frame = self._state_frame(state)
            df = pd.DataFrame({k: pd.Series(v) for k, v in frame.items()})
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            return f"sim_{sim.id}.parquet", EXPORT_MEDIA["parquet"], buf.getvalue()

        if fmt == "hdf5":
            return self._export_hdf5(sim)

        raise ValueError(f"unsupported export format {fmt!r}")

    def _export_hdf5(self, sim: Simulation) -> tuple[str, str, bytes]:
        try:
            import h5py
        except ImportError as exc:
            raise ExportUnavailableError(
                "hdf5 export requires h5py (or tables)"
            ) from exc
        buf = io.BytesIO()
        state = sim.state
        with h5py.File(buf, "w") as f:
            f.attrs["id"] = sim.id
            f.attrs["kind"] = sim.kind
            f.attrs["steps_done"] = sim.steps_done
            f.attrs["owner"] = sim.owner
            for key, value in state.items():
                if key == "history":
                    f.create_dataset(
                        "state/history_json",
                        data=json.dumps(value, default=str),
                        dtype=h5py.string_dtype(encoding="utf-8"),
                    )
                    continue
                arr = _as_numeric_array(value)
                if arr is not None:
                    f.create_dataset(f"state/{key}", data=arr)
            f.create_dataset(
                "state/params_json",
                data=json.dumps(sim.params, default=str),
                dtype=h5py.string_dtype(encoding="utf-8"),
            )
        return f"sim_{sim.id}.h5", EXPORT_MEDIA["hdf5"], buf.getvalue()

    @staticmethod
    def _state_frame(state: dict) -> dict[str, list]:
        """Flatten state into column -> list-of-values for tabular export."""
        frame: dict[str, list] = {}
        for key, value in state.items():
            if key in ("kind", "history", "params"):
                continue
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                frame[key] = [float(value)]
            elif isinstance(value, str):
                frame[key] = [value]
            elif isinstance(value, list):
                if value and all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in value
                ):
                    frame[key] = [float(v) for v in value]
                elif value and all(isinstance(v, list) for v in value):
                    width = len(value[0]) if value[0] else 0
                    for j in range(width):
                        col = []
                        for row in value:
                            try:
                                v = row[j] if j < len(row) else float("nan")
                                col.append(
                                    float(v)
                                    if not isinstance(v, (list, dict))
                                    else float("nan")
                                )
                            except (TypeError, ValueError):
                                col.append(float("nan"))
                        frame[f"{key}_{j}"] = col
                elif value and all(isinstance(v, dict) for v in value):
                    # list of row-dicts (e.g. physics "bodies") -> one column per field
                    field_keys = sorted({fk for row in value for fk in row.keys()})
                    for fk in field_keys:
                        frame[f"{key}.{fk}"] = [
                            row.get(fk) if row.get(fk) is not None else float("nan")
                            for row in value
                        ]
        return frame

    @staticmethod
    def _csv_stdlib(frame: dict[str, list]) -> str:
        import csv as _csv

        if not frame:
            return ""
        keys = list(frame.keys())
        nrows = max(len(v) for v in frame.values())
        buf = io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(keys)
        for i in range(nrows):
            row = []
            for k in keys:
                col = frame[k]
                row.append(col[i] if i < len(col) else "")
            writer.writerow(row)
        return buf.getvalue()

    # -- report ------------------------------------------------------------------
    def report(self, sim_id: str) -> dict:
        sim = self.get(sim_id)
        state = sim.state
        history = state.get("history") if isinstance(state.get("history"), list) else []

        metrics: list[str] = []
        if history and isinstance(history[0], dict):
            metrics = [k for k in history[0] if k != "t"]

        series = []
        for name in metrics:
            series.append(
                {
                    "name": f"{sim.kind}.{name}",
                    "x": [float(e.get("t", 0.0)) for e in history],
                    "y": [float(e.get(name, 0.0)) for e in history],
                }
            )

        numeric_cols = SimulationService._numeric_columns(state)
        stats: dict[str, dict] = {}
        for name, values in numeric_cols.items():
            if not values:
                continue
            stats[name] = _describe(values)

        histograms: list[dict] = []
        for name, value in state.items():
            if name in ("kind", "history", "params", "width", "height") or isinstance(
                value, (str, bool)
            ):
                continue
            flat = _flatten_numbers(value)
            if flat and len(flat) >= 2:
                histograms.append({"name": name, "values": flat, "bins": 20})

        summary = {
            "id": sim.id,
            "kind": sim.kind,
            "owner": sim.owner,
            "steps_done": sim.steps_done,
            "t": float(state.get("t", 0.0)),
            "status": "ok",
            "engine_backend": self._backends.get(sim.id, "mock"),
            "history_points": len(history),
        }
        return {
            "summary": summary,
            "stats": stats,
            "charts_data": {"series": series, "histograms": histograms},
        }

    @staticmethod
    def _numeric_columns(state: dict) -> dict[str, list[float]]:
        cols: dict[str, list[float]] = {}

        def walk(prefix: str, value: Any) -> None:
            if isinstance(value, bool) or value is None or isinstance(value, str):
                return
            if isinstance(value, (int, float)):
                cols.setdefault(prefix, []).append(float(value))
            elif isinstance(value, list):
                if value and all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in value
                ):
                    cols.setdefault(prefix, []).extend(float(v) for v in value)
                elif value and all(isinstance(v, list) for v in value):
                    flat = _flatten_numbers(value)
                    if flat:
                        cols.setdefault(prefix, []).extend(flat)
            elif isinstance(value, dict):
                for k, v in value.items():
                    walk(f"{prefix}.{k}" if prefix else str(k), v)

        for key, value in state.items():
            if key in ("kind", "history", "params"):
                continue
            walk(str(key), value)
        return cols


def _as_numeric_array(value: Any) -> Any:
    """Convert JSON-safe values into a numpy array (or None)."""
    try:
        import numpy as np
    except ImportError:
        return None
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return None
    if isinstance(value, (int, float)):
        return np.asarray([float(value)])
    if isinstance(value, list):
        flat = _flatten_numbers(value)
        if flat:
            return np.asarray(flat)
    return None


def _flatten_numbers(value: Any) -> list[float]:
    out: list[float] = []

    def walk(v: Any) -> None:
        if isinstance(v, bool) or v is None or isinstance(v, str):
            return
        if isinstance(v, (int, float)):
            out.append(float(v))
        elif isinstance(v, list):
            for item in v:
                walk(item)
        elif isinstance(v, dict):
            for item in v.values():
                walk(item)

    walk(value)
    return out


def _describe(values: list[float]) -> dict[str, float]:
    """Lightweight numeric summary without pandas."""
    n = len(values)
    if n == 0:
        return {"count": 0, "min": None, "max": None, "mean": None, "std": None}
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    ordered = sorted(values)
    lo, hi = ordered[0], ordered[-1]
    q25 = ordered[int(0.25 * (n - 1))]
    q50 = ordered[int(0.50 * (n - 1))]
    q75 = ordered[int(0.75 * (n - 1))]
    return {
        "count": n,
        "min": round(lo, 6),
        "max": round(hi, 6),
        "mean": round(mean, 6),
        "std": round(variance**0.5, 6),
        "q25": round(q25, 6),
        "median": round(q50, 6),
        "q75": round(q75, 6),
    }


service = SimulationService()
