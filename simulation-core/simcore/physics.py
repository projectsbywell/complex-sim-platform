"""
physics.py — 2-D rigid body simulation (circle colliders)
=========================================================

Simulates *n* circular rigid bodies interacting under gravity with
friction, restitution, and impulse-based collision response (both
circle–circle and circle–wall).

Parameters
----------
n : int
    Number of bodies (default 20).
gravity : float
    Downward acceleration magnitude (default 9.81).
friction : float
    Friction coefficient applied to tangential velocity on contact
    in [0, 1] (default 0.3).
restitution : float
    Coefficient of restitution for all collisions in [0, 1] (default 0.6).
bounds : tuple[float, float]
    Domain width and height (default (100.0, 100.0)).
seed : int | None
    RNG seed (default None).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from .base import Simulatable, seed_rng

_DEFAULTS: Dict[str, Any] = {
    "n": 20,
    "gravity": 9.81,
    "friction": 0.3,
    "restitution": 0.6,
    "bounds": (100.0, 100.0),
    "seed": None,
}


class _Body:
    """Lightweight rigid body record."""

    __slots__ = ("x", "y", "vx", "vy", "mass", "radius")

    def __init__(
        self, x: float, y: float, vx: float, vy: float,
        mass: float, radius: float,
    ) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.mass = mass
        self.radius = radius


class PhysicsSimulation(Simulatable):
    """2-D rigid body simulation with impulse-based collision resolution."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        merged = {**_DEFAULTS, **(params or {})}
        self._params: Dict[str, Any] = dict(merged)
        self._rng = seed_rng(self._params["seed"])
        n: int = int(self._params["n"])
        w, h = self._params["bounds"]

        self._bodies: list[_Body] = []
        for _ in range(n):
            r = self._rng.uniform(1.0, 4.0)
            mass = r * r * np.pi  # uniform density disk
            body = _Body(
                x=self._rng.uniform(r, w - r),
                y=self._rng.uniform(r, h - r),
                vx=self._rng.uniform(-5.0, 5.0),
                vy=self._rng.uniform(-5.0, 5.0),
                mass=float(mass),
                radius=float(r),
            )
            self._bodies.append(body)

        self._step_count: int = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_circle_circle(self, a: _Body, b: _Body, restitution: float) -> None:
        dx = b.x - a.x
        dy = b.y - a.y
        dist_sq = dx * dx + dy * dy
        min_d = a.radius + b.radius
        if dist_sq >= min_d * min_d or dist_sq == 0.0:
            return
        dist = dist_sq ** 0.5
        nx, ny = dx / dist, dy / dist

        dvx = a.vx - b.vx
        dvy = a.vy - b.vy
        dvn = dvx * nx + dvy * ny
        if dvn <= 0:
            return

        inv_a = 1.0 / a.mass
        inv_b = 1.0 / b.mass
        j = (1 + restitution) * dvn / (inv_a + inv_b)

        a.vx -= j * inv_a * nx
        a.vy -= j * inv_a * ny
        b.vx += j * inv_b * nx
        b.vy += j * inv_b * ny

        overlap = (min_d - dist) * 0.5
        a.x -= nx * overlap
        a.y -= ny * overlap
        b.x += nx * overlap
        b.y += ny * overlap

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        if dt <= 0:
            return
        g = float(self._params["gravity"])
        mu = float(self._params["friction"])
        rest = float(self._params["restitution"])
        w, h = self._params["bounds"]

        bodies = self._bodies

        # --- Integration (semi-implicit Euler) ---
        for b in bodies:
            b.vy += g * dt
            b.vx *= (1 - mu * dt)
            b.vy *= (1 - mu * dt)
            b.x += b.vx * dt
            b.y += b.vy * dt

        # --- Wall collisions ---
        for b in bodies:
            r = b.radius
            if b.x - r < 0:
                b.x = r
                b.vx = abs(b.vx) * rest
                b.vy *= (1 - mu)
            elif b.x + r > w:
                b.x = w - r
                b.vx = -abs(b.vx) * rest
                b.vy *= (1 - mu)
            if b.y - r < 0:
                b.y = r
                b.vy = abs(b.vy) * rest
                b.vx *= (1 - mu)
            elif b.y + r > h:
                b.y = h - r
                b.vy = -abs(b.vy) * rest
                b.vx *= (1 - mu)

        # --- Body–body collisions (brute-force, fine for n << 1000) ---
        nb = len(bodies)
        for i in range(nb):
            for j in range(i + 1, nb):
                self._resolve_circle_circle(bodies[i], bodies[j], rest)

        self._step_count += 1

    def get_state(self) -> Dict[str, Any]:
        return {
            "bodies": [
                {
                    "x": b.x,
                    "y": b.y,
                    "vx": b.vx,
                    "vy": b.vy,
                    "mass": b.mass,
                    "radius": b.radius,
                }
                for b in self._bodies
            ],
            "step": self._step_count,
        }

    def set_state(self, d: Dict[str, Any]) -> None:
        self._bodies = [
            _Body(**bd) for bd in d["bodies"]
        ]
        self._step_count = int(d.get("step", 0))

    def get_params(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_params(self, p: Dict[str, Any]) -> None:
        self._params.update(p)
