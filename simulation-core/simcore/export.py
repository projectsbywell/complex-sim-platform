"""
export.py — Multi-format state export
=====================================

Functions for exporting a simulation state dict to CSV, JSON, Parquet, or
HDF5.  Parquet and HDF5 gracefully fall back to their lightweight
alternatives if the required libraries (``pandas``, ``pyarrow``,
``h5py``) are not installed, so callers never experience a crash.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np


def _json_default(obj: Any) -> Any:
    """Fallback serialiser for NumPy types."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _flatten_state(state: Dict[str, Any]) -> list[dict]:
    """Convert a simulation state dict into a list of row-dicts.

    This is a best-effort flattening; callers who want precise control
    should use a format-specific exporter.
    """
    rows: list[dict] = []

    # Particles
    if "positions" in state and isinstance(state["positions"], list):
        positions = state["positions"]
        velocities = state.get("velocities", [[0, 0]] * len(positions))
        for i, (pos, vel) in enumerate(zip(positions, velocities)):
            row: dict[str, Any] = {"particle_id": i, "x": pos[0], "y": pos[1]}
            if i < len(vel):
                row["vx"] = vel[0]
                row["vy"] = vel[1]
            rows.append(row)
        return rows

    # Bodies
    if "bodies" in state and isinstance(state["bodies"], list):
        for i, b in enumerate(state["bodies"]):
            rows.append({"body_id": i, **b})
        return rows

    # History arrays (SIR, Lotka)
    if "history" in state and isinstance(state["history"], list):
        for i, h in enumerate(state["history"]):
            rows.append({"step_idx": i, **h})
        return rows

    # Neural training curve
    if "loss_history" in state and isinstance(state["loss_history"], list):
        for i, v in enumerate(state["loss_history"]):
            try:
                rows.append({"step_idx": i, "loss": float(v)})
            except (TypeError, ValueError):
                continue
        if rows:
            return rows

    # Grids (ecosystem / fluid)
    for grid_key in ("vegetation", "herbivores", "carnivores", "density", "vx", "vy"):
        if grid_key in state and isinstance(state[grid_key], list):
            grid = state[grid_key]
            for r_idx, row_data in enumerate(grid):
                for c_idx, val in enumerate(row_data):
                    rows.append(
                        {
                            "grid": grid_key,
                            "row": r_idx,
                            "col": c_idx,
                            "value": val,
                        }
                    )
            return rows

    # Scalar fallback
    scalars = {k: v for k, v in state.items() if isinstance(v, (int, float, str, bool))}
    if scalars:
        rows.append(scalars)
    return rows


# -----------------------------------------------------------------------
# Export functions
# -----------------------------------------------------------------------


def export_json(state: Dict[str, Any], path: str | Path) -> None:
    """Write *state* as pretty-printed JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, default=_json_default), encoding="utf-8")


def export_csv(state: Dict[str, Any], path: str | Path) -> None:
    """Write *state* to CSV (best-effort flattening)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = _flatten_state(state)
    if not rows:
        rows = [{"state": json.dumps(state, default=_json_default)}]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def export_parquet(state: Dict[str, Any], path: str | Path) -> None:
    """Write *state* to Parquet.

    Falls back to CSV (with ``.csv`` suffix) if ``pyarrow`` or ``pandas``
    is not installed.
    """
    try:
        import pandas as pd

        rows = _flatten_state(state)
        if not rows:
            rows = [{"state": json.dumps(state, default=_json_default)}]
        df = pd.DataFrame(rows)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(p), index=False)
    except Exception:
        fallback = Path(path).with_suffix(".csv")
        export_csv(state, fallback)


def export_hdf5(state: Dict[str, Any], path: str | Path) -> None:
    """Write *state* to HDF5.

    Falls back to JSON (with ``.json`` suffix) if ``h5py`` is not installed.
    """
    try:
        import h5py

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        with h5py.File(str(p), "w") as f:
            # Store metadata
            meta = {
                k: v for k, v in state.items() if isinstance(v, (int, float, str, bool))
            }
            for k, v in meta.items():
                f.attrs[k] = v

            # Store arrays
            for key, val in state.items():
                if isinstance(val, list):
                    try:
                        arr = np.array(val)
                        if arr.dtype.kind in ("f", "i", "u"):
                            f.create_dataset(key, data=arr)
                        else:
                            # Non-numeric list of lists — store as JSON bytes
                            f.create_dataset(
                                key,
                                data=np.bytes_(json.dumps(val, default=_json_default)),
                            )
                    except (ValueError, TypeError):
                        f.create_dataset(
                            key,
                            data=np.bytes_(json.dumps(val, default=_json_default)),
                        )
    except Exception:
        fallback = Path(path).with_suffix(".json")
        export_json(state, fallback)
