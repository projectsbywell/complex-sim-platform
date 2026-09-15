#!/usr/bin/env python3
"""
example_run.py — Run all five simulation kinds and save results
================================================================

Executes each simulation for 50 steps, serialises the final state to
``examples-data/``, and prints a summary.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running from the package root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from simcore import SimulationEngine, save_json  # noqa: E402
from simcore.export import export_csv  # noqa: E402

STEPS = 50
DATA_DIR = Path(__file__).resolve().parent / "examples-data"
DATA_DIR.mkdir(exist_ok=True)


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def main() -> None:
    kinds = [
        (
            "particles",
            {
                "n": 100,
                "gravity": 9.81,
                "damping": 0.999,
                "restitution": 0.8,
                "bounds": (100.0, 100.0),
                "seed": 42,
            },
            0.01,
        ),
        (
            "fluids",
            {
                "size": 32,
                "viscosity": 1e-4,
                "diffusion": 1e-6,
                "buoyancy": 0.5,
                "seed": 42,
            },
            0.1,
        ),
        (
            "physics",
            {
                "n": 30,
                "gravity": 9.81,
                "friction": 0.3,
                "restitution": 0.6,
                "bounds": (100.0, 100.0),
                "seed": 42,
            },
            0.01,
        ),
        (
            "neural",
            {
                "layers": [4, 8, 4, 1],
                "activation": "relu",
                "loss": "mse",
                "optimiser": "adam",
                "seed": 42,
            },
            0.0,
        ),
        (
            "bio",
            {
                "model": "sir",
                "n_pop": 1000,
                "i0": 10,
                "r0": 0,
                "beta": 0.3,
                "gamma": 0.1,
                "seed": 42,
            },
            1.0,
        ),
    ]

    # Extra bio models
    bio_extra = [
        (
            "bio_lotka",
            {
                "model": "lotka",
                "prey0": 40.0,
                "pred0": 9.0,
                "alpha": 1.1,
                "lotka_beta": 0.4,
                "delta": 0.1,
                "lotka_gamma": 0.4,
                "seed": 42,
            },
            0.1,
        ),
        (
            "bio_eco",
            {
                "model": "eco",
                "grid_size": 32,
                "veg_init": 0.5,
                "herb_init": 0.05,
                "carn_init": 0.01,
                "seed": 42,
            },
            1.0,
        ),
    ]

    print(f"[{_ts()}] Simulation Core Example Run")
    print(f"[{_ts()}] Data directory: {DATA_DIR}")
    print()

    # --- Neural training demo ---
    print("=" * 60)
    print("  NEURAL TRAINING DEMO")
    print("=" * 60)

    import numpy as np

    eng_n = SimulationEngine(
        "neural",
        {
            "layers": [2, 8, 1],
            "activation": "relu",
            "loss": "mse",
            "optimiser": "adam",
            "seed": 42,
        },
    )
    # XOR problem
    X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=float)
    y = np.array([[0], [1], [1], [0]], dtype=float)
    eng_n.set_params({"lr": 0.05})
    for _ in range(STEPS):
        eng_n.step(0.0)

    # Actually train
    neural_sim = eng_n._sim  # access underlying sim
    history = neural_sim.train(X, y, epochs=STEPS, lr=0.05)  # type: ignore[attr-defined]
    preds = neural_sim.predict(X)  # type: ignore[attr-defined]
    print(f"  XOR predictions after {STEPS} epochs:")
    for inp, pred, target in zip(X, preds, y):
        print(f"    {inp} -> {pred[0]:.4f}  (target {target[0]:.0f})")
    print(f"  Final loss: {history[-1]:.6f}")
    print()

    # Save neural state
    save_json(eng_n.get_state(), DATA_DIR / "neural_state.json")
    print("  Saved: neural_state.json")
    print()

    # --- Other simulations ---
    for name, params, dt in kinds:
        if name == "neural":
            continue  # already done
        print("=" * 60)
        print(f"  {name.upper()}")
        print("=" * 60)

        t0 = time.perf_counter()
        eng = SimulationEngine(name, params)  # type: ignore[arg-type]

        # Fluids: inject some density/velocity
        if name == "fluids":
            sim_fluid = eng._sim
            for xi in range(10, 20):
                for yi in range(10, 20):
                    sim_fluid.add_density(xi, yi, 10.0)  # type: ignore[attr-defined]
                    sim_fluid.add_velocity(xi, yi, 2.0, 0.5)  # type: ignore[attr-defined]

        eng.run(steps=STEPS, dt=dt)
        elapsed = time.perf_counter() - t0

        state = eng.get_state()
        # Brief summary
        summary = _summarise(name, state)
        print(f"  Steps: {STEPS}, dt: {dt}, elapsed: {elapsed:.4f}s")
        print(f"  Summary: {summary}")

        # Save JSON
        jpath = DATA_DIR / f"{name}_state.json"
        save_json(state, jpath)
        print(f"  Saved: {jpath.name}")

        # Save CSV
        cpath = DATA_DIR / f"{name}_state.csv"
        export_csv(state, cpath)
        print(f"  Saved: {cpath.name}")
        print()

    # --- Extra bio models ---
    for name, params, dt in bio_extra:
        print("=" * 60)
        print(f"  {name.upper()}")
        print("=" * 60)
        t0 = time.perf_counter()
        eng = SimulationEngine("bio", params)
        eng.run(steps=STEPS, dt=dt)
        elapsed = time.perf_counter() - t0
        state = eng.get_state()
        summary = _summarise(name, state)
        print(f"  Steps: {STEPS}, dt: {dt}, elapsed: {elapsed:.4f}s")
        print(f"  Summary: {summary}")
        jpath = DATA_DIR / f"{name}_state.json"
        save_json(state, jpath)
        print(f"  Saved: {jpath.name}")
        print()

    print(f"[{_ts()}] All simulations completed. Output in {DATA_DIR}/")


def _summarise(kind: str, state: dict) -> str:
    """Return a one-line human-readable summary of the final state."""
    if kind == "particles":
        n = len(state.get("positions", []))
        return f"particles={n}, step={state.get('step', '?')}"
    if kind == "fluids":
        density = state.get("density", [[0]])
        import numpy as np

        arr = np.array(density)
        return f"grid={state.get('grid_size', '?')}, max_density={arr.max():.4f}"
    if kind == "physics":
        n = len(state.get("bodies", []))
        return f"bodies={n}, step={state.get('step', '?')}"
    if kind == "neural":
        arch = state.get("arch", [])
        lh = state.get("loss_history", [])
        last_loss = lh[-1] if lh else "?"
        return f"arch={arch}, final_loss={last_loss}"
    if "s" in state:
        return f"S={state['s']:.1f}, I={state['i']:.1f}, R={state['r']:.1f}"
    if "prey" in state:
        return f"prey={state['prey']:.2f}, pred={state['pred']:.2f}"
    if "vegetation" in state:
        import numpy as np

        v = np.mean(state["vegetation"])
        h = np.mean(state["herbivores"])
        c = np.mean(state["carnivores"])
        return f"veg={v:.3f}, herb={h:.3f}, carn={c:.3f}"
    return str(state)[:120]


if __name__ == "__main__":
    main()
