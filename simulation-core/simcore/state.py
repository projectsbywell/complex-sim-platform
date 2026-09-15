"""
state.py — State serialisation and deserialization
==================================================

Provides compact helpers for persisting simulation state to disk and
converting it to strings.
"""

from __future__ import annotations

import json
import csv
import io
from pathlib import Path
from typing import Any, Dict

from .export import _json_default  # reuse the NumPy-safe default handler


def to_json_str(state: Dict[str, Any], indent: int = 2) -> str:
    """Return a JSON string representation of *state*."""
    return json.dumps(state, indent=indent, default=_json_default)


def save_json(state: Dict[str, Any], path: str | Path) -> None:
    """Write *state* as pretty-printed JSON to *path*."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(to_json_str(state), encoding="utf-8")


def load_json(path: str | Path) -> Dict[str, Any]:
    """Load and return the state dict from a JSON file at *path*."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"State file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def to_csv(state: Dict[str, Any], path: str | Path) -> None:
    """Export *state* to a CSV file.

    Heuristic: if *state* contains a ``"positions"`` key (particles) or a
    flat list of scalars, rows are written directly.  For nested dicts the
    top-level keys become columns.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)

        # Particles-style: list of row-dicts
        if "positions" in state and isinstance(state["positions"], list):
            positions = state["positions"]
            velocities = state.get("velocities", [[0.0, 0.0]] * len(positions))
            writer.writerow(["x", "y", "vx", "vy"])
            for pos, vel in zip(positions, velocities):
                writer.writerow([pos[0], pos[1], vel[0], vel[1]])
            return

        # Bodies-style (physics)
        if "bodies" in state and isinstance(state["bodies"], list):
            bodies = state["bodies"]
            writer.writerow(["x", "y", "vx", "vy", "mass", "radius"])
            for b in bodies:
                writer.writerow(
                    [b["x"], b["y"], b["vx"], b["vy"], b["mass"], b["radius"]]
                )
            return

        # SIR / Lotka — top-level scalars
        scalars = {
            k: v
            for k, v in state.items()
            if isinstance(v, (int, float, str)) and k != "step"
        }
        if scalars:
            writer.writerow(list(scalars.keys()))
            writer.writerow(list(scalars.values()))
            return

        # History array (e.g. SIR history)
        if (
            "history" in state
            and isinstance(state["history"], list)
            and state["history"]
        ):
            hist = state["history"]
            writer.writerow(list(hist[0].keys()))
            for row in hist:
                writer.writerow(list(row.values()))
            return

        # Ecosystem grids — flatten to CSV per-grid
        for grid_key in (
            "vegetation",
            "herbivores",
            "carnivores",
            "density",
            "vx",
            "vy",
        ):
            if grid_key in state and isinstance(state[grid_key], list):
                for row in state[grid_key]:
                    writer.writerow(row)
                return

        # Generic fallback: list all scalar / short-list values
        flat = {
            k: v for k, v in state.items() if isinstance(v, (int, float, str, bool))
        }
        if flat:
            writer.writerow(list(flat.keys()))
            writer.writerow(list(flat.values()))
        else:
            writer.writerow(["state"])
            writer.writerow([json.dumps(state, default=_json_default)])
