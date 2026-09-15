"""
bio.py — Biological / ecological simulation models
===================================================

Three selectable models accessed through a unified interface by setting
``model`` to ``"sir"``, ``"lotka"``, or ``"eco"``:

1. **SIR** — Classic susceptible–infected–recovered compartmental model.
2. **Lotka-Volterra** — Predator–prey population dynamics.
3. **Ecosystem grid** — 2-D grid with vegetation, herbivores, and
   carnivores interacting via simple rules.

Parameters
----------
model : str
    One of ``"sir"`` (default), ``"lotka"``, ``"eco"``.
n_pop : int
    Total population for SIR (default 1000).
i0 : int
    Initial infected count for SIR (default 10).
r0 : int
    Initial recovered count for SIR (default 0).
beta : float
    SIR transmission rate (default 0.3).
gamma : float
    SIR recovery rate (default 0.1).
prey0 : float
    Initial prey population for Lotka-Volterra (default 40.0).
pred0 : float
    Initial predator population for Lotka-Volterra (default 9.0).
alpha : float
    Lotka prey birth rate (default 1.1).
lotka_beta : float
    Lotka predation rate (default 0.4).
delta : float
    Lotka predator reproduction rate (default 0.1).
lotka_gamma : float
    Lotka predator death rate (default 0.4).
grid_size : int
    Side length of ecosystem grid (default 64).
veg_init : float
    Initial vegetation density in [0, 1] (default 0.5).
herb_init : float
    Initial herbivore density in [0, 1] (default 0.05).
carn_init : float
    Initial carnivore density in [0, 1] (default 0.01).
seed : int | None
    RNG seed (default None).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from .base import Simulatable, seed_rng

_DEFAULTS: Dict[str, Any] = {
    "model": "sir",
    "n_pop": 1000,
    "i0": 10,
    "r0": 0,
    "beta": 0.3,
    "gamma": 0.1,
    "prey0": 40.0,
    "pred0": 9.0,
    "alpha": 1.1,
    "lotka_beta": 0.4,
    "delta": 0.1,
    "lotka_gamma": 0.4,
    "grid_size": 64,
    "veg_init": 0.5,
    "herb_init": 0.05,
    "carn_init": 0.01,
    "seed": None,
}


# -----------------------------------------------------------------------
# SIR Model
# -----------------------------------------------------------------------
class _SIR:
    """Susceptible–Infected–Recovered compartmental model."""

    def __init__(self, params: Dict[str, Any], rng: np.random.Generator) -> None:
        n = int(params["n_pop"])
        i0 = int(params["i0"])
        r0 = int(params["r0"])
        if float(params["beta"]) < 0 or float(params["gamma"]) < 0:
            raise ValueError("beta/gamma must be >= 0")
        self.s = float(n - i0 - r0)
        self.i = float(i0)
        self.r = float(r0)
        self.beta = float(params["beta"])
        self.gamma = float(params["gamma"])
        self.rng = rng
        self.history: list[Dict[str, float]] = []

    def step(self, dt: float) -> None:
        n = self.s + self.i + self.r
        if n <= 0:
            return
        ds = -self.beta * self.s * self.i / n * dt
        di = (self.beta * self.s * self.i / n - self.gamma * self.i) * dt
        dr = self.gamma * self.i * dt
        self.s += ds
        self.i += di
        self.r += dr
        # Clamp to non-negative
        self.s = max(self.s, 0.0)
        self.i = max(self.i, 0.0)
        self.r = max(self.r, 0.0)
        self.history.append({"s": self.s, "i": self.i, "r": self.r})

    def get_state(self) -> Dict[str, Any]:
        return {"s": self.s, "i": self.i, "r": self.r, "history": self.history}

    def set_state(self, d: Dict[str, Any]) -> None:
        self.s = d["s"]
        self.i = d["i"]
        self.r = d["r"]
        self.history = list(d.get("history", []))


# -----------------------------------------------------------------------
# Lotka-Volterra Model
# -----------------------------------------------------------------------
class _LotkaVolterra:
    """Classic Lotka–Volterra predator–prey ODE system."""

    def __init__(self, params: Dict[str, Any], rng: np.random.Generator) -> None:
        self.prey = float(params["prey0"])
        self.pred = float(params["pred0"])
        self.alpha = float(params["alpha"])
        self.beta = float(params["lotka_beta"])
        self.delta = float(params["delta"])
        self.gamma = float(params["lotka_gamma"])
        self.rng = rng
        self.history: list[Dict[str, float]] = []

    def step(self, dt: float) -> None:
        dprey = (self.alpha * self.prey - self.beta * self.prey * self.pred) * dt
        dpred = (self.delta * self.prey * self.pred - self.gamma * self.pred) * dt
        self.prey += dprey
        self.pred += dpred
        self.prey = max(self.prey, 0.0)
        self.pred = max(self.pred, 0.0)
        self.history.append({"prey": self.prey, "pred": self.pred})

    def get_state(self) -> Dict[str, Any]:
        return {"prey": self.prey, "pred": self.pred, "history": self.history}

    def set_state(self, d: Dict[str, Any]) -> None:
        self.prey = d["prey"]
        self.pred = d["pred"]
        self.history = list(d.get("history", []))


# -----------------------------------------------------------------------
# Ecosystem Grid Model
# -----------------------------------------------------------------------
class _Ecosystem:
    """Grid-based ecosystem with vegetation, herbivores, and carnivores.

    Rules per cell per step:
    * Vegetation grows logistically toward carrying capacity.
    * Herbivores eat adjacent vegetation, reproduce if well-fed, die if starving.
    * Carnivores eat adjacent herbivores, reproduce if well-fed, die if starving.
    * Stochastic death and dispersal (nearest-neighbour diffusion).
    """

    def __init__(self, params: Dict[str, Any], rng: np.random.Generator) -> None:
        n = int(params["grid_size"])
        self.n = n
        self.veg = np.full((n, n), float(params["veg_init"]))
        self.herb = np.zeros((n, n))
        self.carn = np.zeros((n, n))
        # Seed random populations
        mask_h = rng.random((n, n)) < float(params["herb_init"])
        mask_c = rng.random((n, n)) < float(params["carn_init"])
        self.herb[mask_h] = 1.0
        self.carn[mask_c] = 1.0
        self.rng = rng
        self._step_count = 0

        # Tuning constants
        self.veg_growth = 0.1
        self.veg_cap = 1.0
        self.herb_eat_rate = 0.3
        self.herb_repro_rate = 0.05
        self.herb_death_rate = 0.02
        self.carn_eat_rate = 0.4
        self.carn_repro_rate = 0.03
        self.carn_death_rate = 0.03
        self.disperse_prob = 0.05

    def step(self, dt: float) -> None:
        n = self.n
        dti = max(int(dt), 1)  # sub-steps

        for _ in range(dti):
            # --- Vegetation growth ---
            self.veg += self.veg_growth * self.veg * (1 - self.veg / self.veg_cap)
            self.veg = np.clip(self.veg, 0, self.veg_cap)

            # --- Herbivores ---
            # Grazing: consume neighbouring vegetation
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    ni = np.clip(np.arange(n)[:, None] + di, 0, n - 1)
                    nj = np.clip(np.arange(n)[None, :] + dj, 0, n - 1)
                    eaten = np.minimum(
                        self.herb * self.herb_eat_rate / 8.0, self.veg[ni, nj]
                    )
                    self.veg -= eaten

            # Reproduction / death
            repro = (self.herb > 0.1) * self.herb_repro_rate * self.herb
            death = self.herb_death_rate * self.herb
            self.herb += repro - death
            self.herb = np.clip(self.herb, 0, 2.0)
            self.veg = np.clip(self.veg, 0, self.veg_cap)

            # --- Carnivores ---
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    ni = np.clip(np.arange(n)[:, None] + di, 0, n - 1)
                    nj = np.clip(np.arange(n)[None, :] + dj, 0, n - 1)
                    eaten = np.minimum(
                        self.carn * self.carn_eat_rate / 8.0, self.herb[ni, nj]
                    )
                    self.herb -= eaten

            repro_c = (self.carn > 0.05) * self.carn_repro_rate * self.carn
            death_c = self.carn_death_rate * self.carn
            self.carn += repro_c - death_c
            self.carn = np.clip(self.carn, 0, 1.0)
            self.herb = np.clip(self.herb, 0, 2.0)

            # --- Diffusion (simple averaging with neighbours) ---
            new_veg = self.veg.copy()
            new_herb = self.herb.copy()
            new_carn = self.carn.copy()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    ni = np.clip(np.arange(n)[:, None] + di, 0, n - 1)
                    nj = np.clip(np.arange(n)[None, :] + dj, 0, n - 1)
                    new_veg += self.veg[ni, nj]
                    new_herb += self.herb[ni, nj]
                    new_carn += self.carn[ni, nj]
            self.veg = new_veg / 9.0
            self.herb = new_herb / 9.0
            self.carn = new_carn / 9.0

        self._step_count += 1

    def get_state(self) -> Dict[str, Any]:
        return {
            "vegetation": self.veg.tolist(),
            "herbivores": self.herb.tolist(),
            "carnivores": self.carn.tolist(),
            "step": self._step_count,
        }

    def set_state(self, d: Dict[str, Any]) -> None:
        self.veg = np.array(d["vegetation"])
        self.herb = np.array(d["herbivores"])
        self.carn = np.array(d["carnivores"])
        self._step_count = int(d.get("step", 0))

    def get_stats(self) -> Dict[str, float]:
        return {
            "mean_veg": float(np.mean(self.veg)),
            "mean_herb": float(np.mean(self.herb)),
            "mean_carn": float(np.mean(self.carn)),
        }


# -----------------------------------------------------------------------
# Unified Interface
# -----------------------------------------------------------------------
class BioSimulation(Simulatable):
    """Unified wrapper that delegates to SIR, Lotka-Volterra, or Ecosystem."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        merged = {**_DEFAULTS, **(params or {})}
        self._params: Dict[str, Any] = dict(merged)
        self._rng = seed_rng(self._params["seed"])

        model = str(self._params["model"]).lower()
        if model == "sir":
            self._inner: Any = _SIR(self._params, self._rng)
        elif model == "lotka":
            self._inner = _LotkaVolterra(self._params, self._rng)
        elif model == "eco":
            self._inner = _Ecosystem(self._params, self._rng)
        else:
            raise ValueError(
                f"Unknown bio model {model!r}; use 'sir', 'lotka', or 'eco'."
            )
        self._model = model
        self._step_count: int = 0

    def step(self, dt: float) -> None:
        self._inner.step(dt)
        self._step_count += 1

    def get_state(self) -> Dict[str, Any]:
        state = self._inner.get_state()
        state["model"] = self._model
        return state

    def set_state(self, d: Dict[str, Any]) -> None:
        self._inner.set_state(d)

    def get_params(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_params(self, p: Dict[str, Any]) -> None:
        self._params.update(p)
