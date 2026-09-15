"""
base.py — Abstract base, geometry, and utility helpers
=====================================================

Provides the ``Simulatable`` abstract base class that every simulation
module must implement, a lightweight ``Vec2`` dataclass, and small numeric
helpers.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np

# ---------------------------------------------------------------------------
# RNG helper
# ---------------------------------------------------------------------------


def seed_rng(seed: Optional[int]) -> np.random.Generator:
    """Return a deterministic NumPy random Generator seeded with *seed*.

    If *seed* is ``None`` the generator is seeded from OS entropy.
    """
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to the closed interval ``[lo, hi]``."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ---------------------------------------------------------------------------
# Vec2 dataclass
# ---------------------------------------------------------------------------


@dataclass
class Vec2:
    """Minimal 2-D vector used across simulation modules."""

    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> "Vec2":
        return self.__mul__(scalar)

    def __neg__(self) -> "Vec2":
        return Vec2(-self.x, -self.y)

    def dot(self, other: "Vec2") -> float:
        """Dot product."""
        return self.x * other.x + self.y * other.y

    def length(self) -> float:
        """Euclidean length."""
        return (self.x**2 + self.y**2) ** 0.5

    def normalized(self) -> "Vec2":
        """Return a unit vector (zero-length input returns zero vector)."""
        ln = self.length()
        if ln == 0.0:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / ln, self.y / ln)

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> "Vec2":
        return cls(x=d.get("x", 0.0), y=d.get("y", 0.0))


# ---------------------------------------------------------------------------
# Simulatable abstract base
# ---------------------------------------------------------------------------


class Simulatable(abc.ABC):
    """Interface that every simulation module must satisfy.

    Subclasses **must** implement:

    * ``step(dt)`` — advance the simulation by *dt* time-units.
    * ``get_state()`` — serialisable snapshot of the current state.
    * ``set_state(d)`` — restore state from a snapshot dict.
    * ``get_params()`` — return the parameter dict.
    * ``set_params(p)`` — update parameters from a dict.
    """

    @abc.abstractmethod
    def step(self, dt: float) -> None:
        """Advance the simulation by *dt*."""

    @abc.abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """Return a serialisable snapshot of the current state."""

    @abc.abstractmethod
    def set_state(self, d: Dict[str, Any]) -> None:
        """Restore state from a snapshot dict *d*."""

    @abc.abstractmethod
    def get_params(self) -> Dict[str, Any]:
        """Return the current parameter dict."""

    @abc.abstractmethod
    def set_params(self, p: Dict[str, Any]) -> None:
        """Update the current parameters from dict *p*."""
