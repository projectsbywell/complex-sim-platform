"""Supplementary coverage: eco model, state utils, engine errors, roundtrips."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulation-core"))
import pytest

simcore = pytest.importorskip("simcore")
from simcore import SimulationEngine


def test_bio_eco_runs():
    e = SimulationEngine("bio", {"model": "eco"})
    e.run(10, 0.1)
    s = e.get_state()
    assert "vegetation" in s or "herbivores" in s or "step" in s


def test_engine_rejects_unknown_kind():
    with pytest.raises(ValueError):
        SimulationEngine("nope", {})


def test_state_utils(tmp_path):
    from simcore.state import save_json, load_json, to_csv, to_json_str

    e = SimulationEngine("physics", {"n": 4, "seed": 1})
    e.run(3, 0.016)
    js = to_json_str(
        {"kind": "physics", "params": e.get_params(), "state": e.get_state()}
    )
    assert '"physics"' in js
    p = str(tmp_path / "x.csv")
    to_csv(e.get_state(), p)
    assert os.path.exists(p)


def test_roundtrips():
    for kind in ["fluids", "physics", "neural", "bio"]:
        e = SimulationEngine(kind, {})
        e.run(3, 0.02)
        s1 = e.get_state()
        e2 = SimulationEngine(kind, {})
        e2.set_state(s1)
        assert e2.get_state()["step"] == s1["step"] if "step" in s1 else True


def test_fluid_injection_and_params():
    e = SimulationEngine("fluids", {"size": 12, "seed": 1, "pressure_iters": 8})
    e._sim.add_density(5, 5, 10.0)
    e._sim.add_velocity(5, 5, 1.0, -1.0)
    e.run(5, 0.05)
    assert e.get_state()["step"] == 5
    e.set_params({"buoyancy": 0.5})
    assert e.get_params()["buoyancy"] == 0.5


def test_real_parquet_hdf5(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    pytest.importorskip("h5py")
    from simcore.export import export_parquet, export_hdf5

    e = SimulationEngine("particles", {"n": 10, "seed": 1})
    e.run(3, 0.016)
    pp, hh = str(tmp_path / "r.parquet"), str(tmp_path / "r.h5")
    export_parquet(e.get_state(), pp)
    export_hdf5(e.get_state(), hh)
    assert open(pp, "rb").read(4) == b"PAR1"  # magic parquet, não fallback
    assert open(hh, "rb").read(4) == b"\x89HDF"  # magic hdf5 real
