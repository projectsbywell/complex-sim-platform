"""
fluids.py — Stable Fluids 2-D (Jos Stam style)
==============================================

A simplified incompressible fluid solver on an *N × N* Eulerian grid using
the semi-Lagrangian advection scheme from Jos Stam's "Stable Fluids" (1999).

Pipeline per step:
    1. Diffusion  (Gauss-Seidel relaxation on the diffusion equation).
    2. Advection   (semi-Lagrangian, bilinear interpolation).
    3. Projection  (pressure solve via Jacobi iteration, then subtract
       the pressure gradient).

External forces:
    * ``add_density(x, y, amount)``  — inject scalar density.
    * ``add_velocity(x, y, vx, vy)`` — inject velocity impulse.
    * Buoyancy force (optional) pushes velocity upward proportional to
      density.

Parameters
----------
size : int
    Grid resolution (default 64).
viscosity : float
    Kinematic viscosity ν (default 1e-4).
diffusion : float
    Scalar diffusion coefficient (default 1e-6).
buoyancy : float
    Buoyancy strength (default 0.0).
seed : int | None
    RNG seed (default None).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from .base import Simulatable, clamp, seed_rng

_DEFAULTS: Dict[str, Any] = {
    "size": 64,
    "viscosity": 1e-4,
    "diffusion": 1e-6,
    "buoyancy": 0.0,
    "pressure_iters": 20,
    "seed": None,
}

_JACOBI_ITERS: int = 20


def _diffuse(x: np.ndarray, x0: np.ndarray, diff: float, dt: float) -> np.ndarray:
    """Gauss-Seidel relaxation diffusion step (in-place style, returns new array)."""
    n = x.shape[0]
    a = dt * diff * (n - 2) * (n - 2)
    if a <= 0:
        return x0.copy()
    x_new = x.copy()
    for _ in range(4):
        x_new[1:-1, 1:-1] = (
            x0[1:-1, 1:-1]
            + a
            * (x_new[:-2, 1:-1] + x_new[2:, 1:-1] + x_new[1:-1, :-2] + x_new[1:-1, 2:])
        ) / (1 + 4 * a)
    return x_new


def _advect(
    d: np.ndarray, d0: np.ndarray, vx: np.ndarray, vy: np.ndarray, dt: float
) -> np.ndarray:
    """Semi-Lagrangian advection with bilinear interpolation (vectorized).

    Mathematically identical to the scalar loop version: trace each interior
    cell centre backwards along the velocity field, then bilinearly sample
    the source field. Fully vectorized with NumPy advanced indexing.
    """
    n = d.shape[0]
    d_new = d.copy()
    dt0 = dt * (n - 2)

    ii, jj = np.meshgrid(np.arange(1, n - 1), np.arange(1, n - 1), indexing="ij")
    x = np.clip(ii - dt0 * vx[1:-1, 1:-1], 0.5, n - 1.5)
    y = np.clip(jj - dt0 * vy[1:-1, 1:-1], 0.5, n - 1.5)
    i0 = x.astype(np.int64)
    j0 = y.astype(np.int64)
    i1 = i0 + 1
    j1 = j0 + 1
    s1 = x - i0
    s0 = 1.0 - s1
    t1 = y - j0
    t0 = 1.0 - t1
    d_new[1:-1, 1:-1] = s0 * (t0 * d0[i0, j0] + t1 * d0[i0, j1]) + s1 * (
        t0 * d0[i1, j0] + t1 * d0[i1, j1]
    )
    return d_new


def _set_boundary(b: int, x: np.ndarray) -> None:
    """Set boundary conditions: reflect velocity component perpendicular to wall.

    When b == 1 (horizontal velocity u), left/right walls negate the
    perpendicular component.  When b == 2 (vertical velocity v), top/bottom
    walls negate the perpendicular component (Stam convention).
    """
    n = x.shape[0]
    if b == 1:
        x[:, 0] = -x[:, 1]
        x[:, n - 1] = -x[:, n - 2]
    elif b == 2:
        x[0, :] = -x[1, :]
        x[n - 1, :] = -x[n - 2, :]


def _pressure_jacobi(
    p: np.ndarray, div: np.ndarray, iters: int = _JACOBI_ITERS
) -> np.ndarray:
    """Solve pressure Poisson equation via Jacobi iteration.

    div = -∇²p  →  p_new = (Σneighbours - div) / 4
    """
    n = p.shape[0]
    p_new = p.copy()
    for _ in range(iters):
        p_new[1:-1, 1:-1] = (
            p_new[:-2, 1:-1]
            + p_new[2:, 1:-1]
            + p_new[1:-1, :-2]
            + p_new[1:-1, 2:]
            - div[1:-1, 1:-1]
        ) / 4.0
    return p_new


class FluidSimulation(Simulatable):
    """Stable Fluids 2-D solver."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        merged = {**_DEFAULTS, **(params or {})}
        self._params: Dict[str, Any] = dict(merged)
        self._rng = seed_rng(self._params["seed"])
        size = int(self._params["size"])
        if size < 4 or size > 256:
            raise ValueError("size must be in [4, 256]")
        n: int = size + 2  # +2 for boundary cells
        self._n = n
        self._density = np.zeros((n, n))
        self._density_prev = np.zeros((n, n))
        self._vx = np.zeros((n, n))
        self._vy = np.zeros((n, n))
        self._vx_prev = np.zeros((n, n))
        self._vy_prev = np.zeros((n, n))
        self._step_count: int = 0

    # ------------------------------------------------------------------
    # Public injection API
    # ------------------------------------------------------------------

    def add_density(self, x: int, y: int, amount: float) -> None:
        """Inject scalar density at grid cell (*x*, *y*)."""
        i = int(x) + 1
        j = int(y) + 1
        if 0 < i < self._n and 0 < j < self._n:
            self._density_prev[i, j] += amount

    def add_velocity(self, x: int, y: int, vx: float, vy: float) -> None:
        """Inject velocity impulse at grid cell (*x*, *y*)."""
        i = int(x) + 1
        j = int(y) + 1
        if 0 < i < self._n and 0 < j < self._n:
            self._vx_prev[i, j] += vx
            self._vy_prev[i, j] += vy

    # ------------------------------------------------------------------
    # Simulatable interface
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance the fluid by *dt* (diffuse → advect → project)."""
        if dt <= 0:
            return
        vis = float(self._params["viscosity"])
        diff = float(self._params["diffusion"])
        buoy = float(self._params["buoyancy"])

        # --- Add sources (Stam add_source: field += source) ---
        # add_density/add_velocity accumulate into *_prev buffers; fold them
        # into the live fields so injected mass/momentum persists and is
        # diffused/advected instead of being wiped on the next step.
        self._vx += self._vx_prev
        self._vy += self._vy_prev
        self._density += self._density_prev

        # --- Velocity diffusion (source = pre-diffuse snapshot) ---
        vx0 = self._vx.copy()
        vy0 = self._vy.copy()
        self._vx = _diffuse(self._vx, vx0, vis, dt)
        self._vy = _diffuse(self._vy, vy0, vis, dt)
        _set_boundary(1, self._vx)
        _set_boundary(2, self._vy)

        # --- Buoyancy ---
        if buoy != 0.0:
            self._vy -= buoy * self._density * dt

        # --- Advection (semi-Lagrangian, vectorized; source = diffused field) ---
        vx_d = self._vx.copy()
        vy_d = self._vy.copy()
        self._vx = _advect(self._vx, vx_d, vx_d, vy_d, dt)
        self._vy = _advect(self._vy, vy_d, vx_d, vy_d, dt)
        _set_boundary(1, self._vx)
        _set_boundary(2, self._vy)

        # --- Projection (incompressibility) ---
        div = np.zeros((self._n, self._n))
        div[1:-1, 1:-1] = (
            -0.5
            * (
                (self._vx[2:, 1:-1] - self._vx[:-2, 1:-1])
                + (self._vy[1:-1, 2:] - self._vy[1:-1, :-2])
            )
            / self._n
        )
        p = _pressure_jacobi(
            np.zeros_like(div),
            div,
            iters=int(self._params.get("pressure_iters", _JACOBI_ITERS)),
        )
        self._vx[1:-1, 1:-1] -= 0.5 * self._n * (p[2:, 1:-1] - p[:-2, 1:-1])
        self._vy[1:-1, 1:-1] -= 0.5 * self._n * (p[1:-1, 2:] - p[1:-1, :-2])

        # --- Density diffusion & advection (source = pre-diffuse snapshot) ---
        d0 = self._density.copy()
        self._density = _diffuse(self._density, d0, diff, dt)
        d1 = self._density.copy()
        self._density = _advect(self._density, d1, self._vx, self._vy, dt)

        # --- Boundary conditions ---
        _set_boundary(1, self._vx)
        _set_boundary(2, self._vy)

        # --- Swap buffers ---
        self._vx_prev[:] = 0.0
        self._vy_prev[:] = 0.0
        self._density_prev[:] = 0.0

        self._step_count += 1

    def get_state(self) -> Dict[str, Any]:
        return {
            "density": self._density.tolist(),
            "vx": self._vx.tolist(),
            "vy": self._vy.tolist(),
            "step": self._step_count,
            "grid_size": self._n - 2,
        }

    def set_state(self, d: Dict[str, Any]) -> None:
        self._density = np.array(d["density"])
        self._vx = np.array(d["vx"])
        self._vy = np.array(d["vy"])
        self._step_count = int(d.get("step", 0))

    def get_params(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_params(self, p: Dict[str, Any]) -> None:
        self._params.update(p)
