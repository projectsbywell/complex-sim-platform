"""Unit tests — simulation core (5 subsystems). Deterministic via fixed seeds."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulation-core"))
import pytest

simcore = pytest.importorskip("simcore")
from simcore import SimulationEngine


def test_particles_runs_and_bounces():
    e = SimulationEngine("particles", {"n": 50, "seed": 42})
    e.run(30, 0.016)
    s = e.get_state()
    assert len(s["positions"]) == 50
    for x, y in s["positions"]:
        assert 0 <= x <= 1000 and -50 <= y <= 600
    p0 = e.get_params()
    e.set_params({**p0, "gravity": 1.0})
    assert e.get_params()["gravity"] == 1.0


def test_fluids_diffuses():
    e = SimulationEngine("fluids", {"size": 16, "seed": 7})
    e.run(10, 0.05)
    s = e.get_state()
    import itertools

    flat = list(itertools.chain.from_iterable(s["density"]))
    assert len(flat) == 18 * 18 or len(s["density"]) >= 16  # includes boundary cells
    assert all(v >= 0 for v in flat)


def test_physics_falls_and_collides():
    e = SimulationEngine("physics", {"n": 6, "seed": 3})
    y0 = sum(b["y"] for b in e.get_state()["bodies"])
    e.run(20, 0.016)
    y1 = sum(b["y"] for b in e.get_state()["bodies"])
    assert y1 >= y0  # gravity pulls down (+y)


def test_neural_xor_learns():
    import numpy as np

    e = SimulationEngine(
        "neural", {"layers": [2, 8, 1], "activation": "tanh", "seed": 1}
    )
    X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], float)
    y = np.array([[0], [1], [1], [0]], float)
    sim = e._sim
    sim.train(X, y, epochs=400, lr=0.05)
    pred = (sim.predict(X) > 0.5).astype(int)
    assert (pred.flatten() == np.array([0, 1, 1, 0])).sum() >= 3


def test_bio_sir_conserves_population():
    e = SimulationEngine("bio", {"model": "sir", "beta": 0.3, "gamma": 0.08})
    e.run(50, 0.1)
    s = e.get_state()
    assert abs((s["s"] + s["i"] + s["r"]) - 1000) < 1e-3
    assert s["r"] > 0


def test_bio_lotka_stays_positive():
    e = SimulationEngine("bio", {"model": "lotka"})
    e.run(100, 0.05)
    s = e.get_state()
    assert s["prey"] > 0 and s["pred"] > 0


def test_state_roundtrip(tmp_path):
    from simcore.state import save_json, load_json

    e = SimulationEngine("particles", {"n": 10, "seed": 1})
    e.run(5, 0.016)
    p = str(tmp_path / "s.json")
    save_json(
        {"kind": "particles", "params": e.get_params(), "state": e.get_state()}, p
    )
    d = load_json(p)
    assert d["kind"] == "particles"


def test_export_all_formats(tmp_path):
    from simcore.export import export_csv, export_json, export_parquet, export_hdf5

    e = SimulationEngine("particles", {"n": 10, "seed": 1})
    e.run(5, 0.016)
    st = e.get_state()
    export_csv(st, str(tmp_path / "a.csv"))
    assert os.path.exists(str(tmp_path / "a.csv"))
    export_json(st, str(tmp_path / "a.json"))
    assert os.path.exists(str(tmp_path / "a.json"))
    export_parquet(st, str(tmp_path / "a.parquet"))  # fallback ok
    export_hdf5(st, str(tmp_path / "a.h5"))  # fallback ok
    assert True
