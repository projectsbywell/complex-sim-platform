"""
engine.py — SimulationEngine facade
====================================

Single entry-point that instantiates the appropriate simulation module
and exposes a uniform step/run/get/set interface.

Valid kinds: ``"particles"``, ``"fluids"``, ``"physics"``, ``"neural"``,
``"bio"``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .base import Simulatable
from .particles import ParticleSimulation
from .fluids import FluidSimulation
from .physics import PhysicsSimulation
from .neural import NeuralSimulation
from .bio import BioSimulation
from .state import to_json_str

_REGISTRY: Dict[str, type] = {
    "particles": ParticleSimulation,
    "fluids": FluidSimulation,
    "physics": PhysicsSimulation,
    "neural": NeuralSimulation,
    "bio": BioSimulation,
}


class SimulationEngine:
    """Facade that wraps a ``Simulatable`` instance and exposes a uniform API.

    Parameters
    ----------
    kind : str
        One of ``"particles"``, ``"fluids"``, ``"physics"``, ``"neural"``,
        ``"bio"``.
    params : dict
        Parameters forwarded to the underlying simulation class.
    """

    def __init__(self, kind: str, params: Optional[Dict[str, Any]] = None) -> None:
        cls = _REGISTRY.get(kind.lower())
        if cls is None:
            raise ValueError(
                f"Unknown simulation kind {kind!r}; "
                f"valid kinds: {sorted(_REGISTRY)}."
            )
        self._kind: str = kind.lower()
        self._sim: Simulatable = cls(params or {})

    # ------------------------------------------------------------------
    # Uniform interface
    # ------------------------------------------------------------------

    @property
    def kind(self) -> str:
        """Return the simulation kind string."""
        return self._kind

    def step(self, dt: float) -> None:
        """Advance the simulation by *dt*."""
        self._sim.step(dt)

    def run(self, steps: int, dt: float) -> None:
        """Run *steps* iterations, each advancing by *dt*."""
        for _ in range(int(steps)):
            self._sim.step(dt)

    def get_state(self) -> Dict[str, Any]:
        """Return a serialisable snapshot of the current state."""
        return self._sim.get_state()

    def set_state(self, d: Dict[str, Any]) -> None:
        """Restore state from a snapshot dict *d*."""
        self._sim.set_state(d)

    def get_params(self) -> Dict[str, Any]:
        """Return the current parameter dict."""
        return self._sim.get_params()

    def set_params(self, p: Dict[str, Any]) -> None:
        """Update parameters from dict *p*."""
        self._sim.set_params(p)

    def to_json(self, indent: int = 2) -> str:
        """Serialise the full state (kind + params + state) to a JSON string."""
        payload: Dict[str, Any] = {
            "kind": self._kind,
            "params": self.get_params(),
            "state": self.get_state(),
        }
        return json.dumps(payload, indent=indent, default=_json_default)


def _json_default(obj: Any) -> Any:
    """Fallback serialiser for NumPy types."""
    import numpy as np

    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
