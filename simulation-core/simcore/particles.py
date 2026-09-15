"""
particles.py — N-body 2-D particle simulation
==============================================

Simulates *n* point-mass particles in 2-D with:

* Semi-implicit Euler / Verlet integration.
* Uniform gravity field.
* Velocity damping (per-step multiplicative).
* Elastic wall collisions (bounded rectangular domain).
* Particle-particle elastic collisions via spatial hashing (grid-based).

Parameters
----------
n : int
    Number of particles (default 100).
gravity : float
    Downward acceleration magnitude (default 9.81).
damping : float
    Velocity damping factor per step in [0, 1] (default 0.999).
restitution : float
    Coefficient of restitution for all collisions in [0, 1] (default 0.8).
bounds : tuple[float, float]
    Width and height of the simulation domain (default (100.0, 100.0)).
seed : int | None
    RNG seed for reproducibility (default None).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base import Simulatable, Vec2, clamp, seed_rng

_DEFAULTS: Dict[str, Any] = {
    "n": 100,
    "gravity": 9.81,
    "damping": 0.999,
    "restitution": 0.8,
    "bounds": (100.0, 100.0),
    "seed": None,
}

# Spatial hash cell size — particles within the same cell are checked for
# collisions.  Twice the average inter-particle distance is a good default.
_CELL_MULT: float = 2.0


@dataclass
class _Particle:
    """Internal particle record (structure-of-arrays is used externally)."""
    x: float
    y: float
    vx: float
    vy: float
    mass: float
    radius: float


class ParticleSimulation(Simulatable):
    """N-particle 2-D simulation with spatial-hash collision detection."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        merged = {**_DEFAULTS, **(params or {})}
        self._params: Dict[str, Any] = dict(merged)
        self._rng = seed_rng(self._params["seed"])

        n: int = int(self._params["n"])
        if n < 0:
            raise ValueError("n must be >= 0")
        if n > 10000:
            raise ValueError("n too large (max 10000)")
        w, h = self._params["bounds"]

        # Initialise positions uniformly, velocities small random, masses & radii
        self._x = self._rng.uniform(0.1 * w, 0.9 * w, size=n)
        self._y = self._rng.uniform(0.1 * h, 0.9 * h, size=n)
        self._vx = self._rng.uniform(-1.0, 1.0, size=n)
        self._vy = self._rng.uniform(-1.0, 1.0, size=n)
        self._mass = np.ones(n)
        self._radius = np.full(n, 1.0)

        self._step_count: int = 0

    # ------------------------------------------------------------------
    # Spatial hashing helpers
    # ------------------------------------------------------------------

    def _cell_coords(self, cell_size: float) -> Tuple[np.ndarray, np.ndarray]:
        """Return integer (row, col) cell indices for every particle."""
        ix = (self._x / cell_size).astype(int)
        iy = (self._y / cell_size).astype(int)
        return ix, iy

    def _build_grid(self, cell_size: float) -> Dict[Tuple[int, int], List[int]]:
        grid: Dict[Tuple[int, int], List[int]] = {}
        ix, iy = self._cell_coords(cell_size)
        for i in range(len(self._x)):
            key = (int(ix[i]), int(iy[i]))
            if key not in grid:
                grid[key] = []
            grid[key].append(i)
        return grid

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:  # noqa: C901 — intentionally flat
        """Advance simulation by *dt*."""
        n = len(self._x)
        if n == 0 or dt <= 0:
            return

        gravity = float(self._params["gravity"])
        damping = float(self._params["damping"])
        restitution = float(self._params["restitution"])
        w, h = self._params["bounds"]

        # --- Semi-implicit Euler integration ---
        self._vy += gravity * dt
        self._vx *= damping
        self._vy *= damping
        self._x += self._vx * dt
        self._y += self._vy * dt

        # --- Wall collisions ---
        rest = float(restitution)
        for i in range(n):
            r = float(self._radius[i])
            # left / right
            if self._x[i] - r < 0:
                self._x[i] = r
                self._vx[i] = abs(self._vx[i]) * rest
            elif self._x[i] + r > w:
                self._x[i] = w - r
                self._vx[i] = -abs(self._vx[i]) * rest
            # bottom / top
            if self._y[i] - r < 0:
                self._y[i] = r
                self._vy[i] = abs(self._vy[i]) * rest
            elif self._y[i] + r > h:
                self._y[i] = h - r
                self._vy[i] = -abs(self._vy[i]) * rest

        # --- Particle-particle collisions (spatial hash) ---
        avg_r = float(np.mean(self._radius)) if n else 1.0
        cell_size = max(2.0 * avg_r * _CELL_MULT, 1.0)
        grid = self._build_grid(cell_size)

        for key, indices in grid.items():
            ci, cj = key
            # Check 3×3 neighbourhood
            for di in range(-1, 2):
                for dj in range(-1, 2):
                    neighbour = (ci + di, cj + dj)
                    if neighbour not in grid:
                        continue
                    for i in indices:
                        for j in grid[neighbour]:
                            if j <= i:
                                continue
                            dx = self._x[j] - self._x[i]
                            dy = self._y[j] - self._y[i]
                            dist_sq = dx * dx + dy * dy
                            min_dist = self._radius[i] + self._radius[j]
                            if dist_sq < min_dist * min_dist and dist_sq > 0:
                                self._resolve_collision(i, j, dx, dy,
                                                        dist_sq, rest)

        self._step_count += 1

    def _resolve_collision(
        self, i: int, j: int,
        dx: float, dy: float,
        dist_sq: float, restitution: float,
    ) -> None:
        """Resolve an elastic collision between particles *i* and *j*."""
        dist = dist_sq ** 0.5
        nx, ny = dx / dist, dy / dist  # collision normal

        # Relative velocity along normal
        dvx = self._vx[i] - self._vx[j]
        dvy = self._vy[i] - self._vy[j]
        dvn = dvx * nx + dvy * ny

        if dvn <= 0:  # already separating
            return

        m_i = float(self._mass[i])
        m_j = float(self._mass[j])
        impulse = (1 + restitution) * dvn / (m_i + m_j)

        self._vx[i] -= impulse * m_j * nx
        self._vy[i] -= impulse * m_j * ny
        self._vx[j] += impulse * m_i * nx
        self._vy[j] += impulse * m_i * ny

        # Separate overlapping particles equally
        overlap = (self._radius[i] + self._radius[j] - dist) * 0.5
        self._x[i] -= nx * overlap
        self._y[i] -= ny * overlap
        self._x[j] += nx * overlap
        self._y[j] += ny * overlap

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "positions": np.column_stack([self._x, self._y]).tolist(),
            "velocities": np.column_stack([self._vx, self._vy]).tolist(),
            "masses": self._mass.tolist(),
            "radii": self._radius.tolist(),
            "step": self._step_count,
        }

    def set_state(self, d: Dict[str, Any]) -> None:
        pos = np.array(d["positions"])
        vel = np.array(d["velocities"])
        self._x = pos[:, 0].copy()
        self._y = pos[:, 1].copy()
        self._vx = vel[:, 0].copy()
        self._vy = vel[:, 1].copy()
        self._mass = np.array(d.get("masses", np.ones(len(pos))))
        self._radius = np.array(d.get("radii", np.ones(len(pos))))
        self._step_count = int(d.get("step", 0))

    def get_params(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_params(self, p: Dict[str, Any]) -> None:
        self._params.update(p)
        if "seed" in p and p["seed"] is not None:
            self._rng = seed_rng(p["seed"])
