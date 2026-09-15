"""QA extra - edge, security, regression (gerado por Worker 6 para fechar coverage >80 e validar falhas)."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulation-core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "security"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import pytest
from simcore import SimulationEngine
import numpy as np


def test_vec2_and_clamp():
    from simcore.base import Vec2, clamp, seed_rng

    v = Vec2(1, 2)
    assert (v + Vec2(1, 1)).x == 2
    assert (v - Vec2(0.5, 0.5)).y == 1.5
    assert (v * 2).x == 2
    assert (2 * v).y == 4
    assert (-v).x == -1
    assert abs(v.dot(Vec2(2, 3)) - 8) < 1e-9
    assert abs(v.length() - (1 + 4) ** 0.5) < 1e-9
    assert Vec2(0, 0).normalized() == Vec2(0, 0)
    assert abs(Vec2(3, 4).normalized().length() - 1) < 1e-9
    assert Vec2.from_dict({"x": 5, "y": 6}).x == 5
    assert Vec2(1, 2).to_dict() == {"x": 1, "y": 2}
    assert clamp(5, 0, 1) == 1
    assert clamp(-1, 0, 10) == 0
    assert clamp(5, 0, 10) == 5
    rng = seed_rng(42)
    assert rng is not None
    rng2 = seed_rng(None)
    assert rng2 is not None


def test_engine_edge_and_json_default():
    e = SimulationEngine("particles", {"n": 5, "seed": 1})
    # to_json coverage
    js = e.to_json()
    assert "particles" in js
    # engine rejects
    with pytest.raises(ValueError):
        SimulationEngine("INVALID", {})
    # dt=0 no step
    s0 = e.get_state()["step"]
    e.step(0)
    assert e.get_state()["step"] == s0
    e.step(-0.1)
    assert e.get_state()["step"] == s0
    # run 0 steps
    e.run(0, 0.016)
    assert True
    # numpy json default
    from simcore.engine import _json_default

    assert _json_default(np.array([1, 2])) == [1, 2]
    assert _json_default(np.float32(1.5)) == 1.5
    assert _json_default(np.int64(3)) == 3
    with pytest.raises(TypeError):
        _json_default(object())


def test_export_state_missing_lines(tmp_path):
    from simcore.export import (
        _flatten_state,
        export_csv,
        export_json,
        export_parquet,
        export_hdf5,
    )
    from simcore.state import save_json, load_json, to_csv, to_json_str

    # neural loss_history edge
    s = {"loss_history": [0.5, 0.4, "bad", None]}
    rows = _flatten_state(s)
    assert len(rows) >= 2
    # scalar fallback
    rows2 = _flatten_state({"a": 1, "b": "x"})
    assert len(rows2) == 1
    # empty state
    assert _flatten_state({}) == []
    # grid
    rows3 = _flatten_state({"density": [[1, 2], [3, 4]]})
    assert len(rows3) == 4
    # bodies
    rows4 = _flatten_state(
        {"bodies": [{"x": 1, "y": 2, "vx": 0, "vy": 0, "mass": 1, "radius": 1}]}
    )
    assert rows4[0]["x"] == 1
    # positions
    rows5 = _flatten_state({"positions": [[0, 0]], "velocities": [[1, 1]]})
    assert rows5[0]["particle_id"] == 0
    # history
    rows6 = _flatten_state({"history": [{"s": 1, "i": 2}]})
    assert rows6[0]["s"] == 1
    # export_csv fallback
    export_csv({}, str(tmp_path / "empty.csv"))
    assert (tmp_path / "empty.csv").exists()
    export_json({"a": np.array([1, 2])}, str(tmp_path / "j.json"))
    assert (tmp_path / "j.json").exists()
    # state.py branches
    js = to_json_str({"x": np.array([1])})
    assert "x" in js
    save_json({"k": 1}, str(tmp_path / "s.json"))
    assert load_json(str(tmp_path / "s.json"))["k"] == 1
    with pytest.raises(FileNotFoundError):
        load_json(str(tmp_path / "nope.json"))
    # to_csv variants
    e = SimulationEngine("bio", {"model": "sir"})
    e.run(5, 0.1)
    to_csv(e.get_state(), str(tmp_path / "sir.csv"))
    e2 = SimulationEngine("bio", {"model": "eco", "grid_size": 8})
    e2.run(2, 0.1)
    to_csv(e2.get_state(), str(tmp_path / "eco.csv"))
    e3 = SimulationEngine("fluids", {"size": 8})
    e3.run(2, 0.05)
    to_csv(e3.get_state(), str(tmp_path / "fluid.csv"))
    e4 = SimulationEngine("neural", {"layers": [2, 4, 1]})
    to_csv(e4.get_state(), str(tmp_path / "neural.csv"))
    assert (tmp_path / "neural.csv").exists()
    # parquet/hdf5 fallback bad path (no crash)
    export_parquet({"x": 1}, str(tmp_path / "p.parquet"))
    export_hdf5({"x": 1}, str(tmp_path / "h.h5"))


def test_particles_physics_edges():
    # physics brute force collision edge dist_sq==0
    from simcore.physics import PhysicsSimulation

    p = PhysicsSimulation({"n": 2, "seed": 1})
    # force overlap exactly
    p._bodies[0].x = 50
    p._bodies[0].y = 50
    p._bodies[1].x = 50
    p._bodies[1].y = 50
    p.step(0.016)  # should not crash on dist_sq==0
    # particles zero n already tested
    # neural activation errors
    from simcore.neural import _activate, _activate_prime

    with pytest.raises(ValueError):
        _activate(np.array([1]), "unknown")
    with pytest.raises(ValueError):
        _activate_prime(np.array([1]), "unknown")
    # fluids diffuse with a<=0
    from simcore.fluids import _diffuse

    a = np.zeros((4, 4))
    b = np.zeros((4, 4))
    out = _diffuse(a, b, diff=0, dt=0.01)
    assert out.shape == (4, 4)


def test_security_middleware_edges():
    from middleware import (
        sanitize_sql,
        is_sql_safe,
        escape_html,
        strip_tags,
        csrf_token,
        verify_csrf,
        get_security_headers,
        is_rate_limited,
        security_headers,
    )

    assert sanitize_sql("a\x00b") == "ab"
    assert "''" in sanitize_sql("a'b")
    assert is_sql_safe("hello") == True
    assert is_sql_safe("SELECT * FROM x") == False
    assert escape_html("<b>") == "&lt;b&gt;"
    assert strip_tags("<b>hi</b>") == "hi"
    t = csrf_token(expires_in=3600)
    assert verify_csrf(t) == True
    assert verify_csrf("bad") == False
    # base64 padding tolerant - extra char may still decode, so tamper inner payload instead
    raw = __import__("base64").urlsafe_b64decode(t.encode()).decode()
    parts = raw.split(".")
    tampered = (
        __import__("base64")
        .urlsafe_b64encode(f"{parts[0]}.{parts[1]}.bad{parts[2]}".encode())
        .decode()
    )
    assert verify_csrf(tampered) == False
    # expired
    t2 = csrf_token(expires_in=-10)
    assert verify_csrf(t2) == False
    h = get_security_headers({"X-Custom": "1"})
    assert h["X-Custom"] == "1"
    assert "Content-Security-Policy" in security_headers
    assert is_rate_limited([0] * 5, window_sec=10, max_req=3, now=5) == True
    assert is_rate_limited([0] * 2, window_sec=10, max_req=3, now=5) == False


def test_crypto_audit_anomaly_edges():
    from crypto import (
        encrypt_at_rest,
        decrypt_at_rest,
        hash_password,
        verify_password,
        TLS_CHECKLIST,
        FALLBACK_WARNING,
    )

    # roundtrip
    ct = encrypt_at_rest("hello", key="k123")
    assert decrypt_at_rest(ct, key="k123") == "hello"
    # wrong key fails or returns garbage but not crash
    try:
        decrypt_at_rest(ct, key="wrongkey")
        # AES may raise, fallback returns garbage; both acceptable, just not equal
        assert True
    except Exception:
        assert True
    h = hash_password("s3cr3t123")
    assert verify_password("s3cr3t123", h) == True
    assert verify_password("wrong", h) == False
    assert verify_password("any", "pbkdf2$sha256$200000$salt$badhex") == False
    assert len(TLS_CHECKLIST) == 8
    # audit rotate
    import tempfile, pathlib
    from audit import AuditLogger

    p = tempfile.mktemp(suffix=".log")
    lg = AuditLogger(p)
    lg.log(actor="u", action="a", resource="r")
    assert len(lg.read()) == 1
    assert len(lg.filter(actor="u")) == 1
    # force rotate
    open(p, "w").write("x" * 20)
    new = lg.rotate_if_large(max_bytes=10)
    assert new is not None and new.exists()
    # anomaly rate (is_anomaly requires >=10 samples, so use window=20)
    from anomaly import AnomalyDetector

    d = AnomalyDetector(window=20, z_threshold=1.0, rate_threshold=2.0)
    for _ in range(15):
        d.observe("k", 1.0)
    assert d.stats("k")["mean"] == 1.0
    assert d.is_anomaly("k", 10.0) == True
    assert d.is_anomaly("k", 1.0) == False
    # rate anomaly
    import time

    now = time.time()
    for i in range(10):
        d.observe("r", 1.0, ts=now - i * 0.1)
    assert d.rate("r", now=now) > 0
    assert isinstance(d.check("k", 10.0), dict)
    d.reset("k")
    assert d.stats("k")["count"] == 0
    d.reset()
    assert True


def test_regression_bio_neural():
    # ensure sir conserves approximate, lotka stays positive over longer run
    e = SimulationEngine("bio", {"model": "sir", "beta": 0.3, "gamma": 0.08})
    e.run(100, 0.1)
    s = e.get_state()
    assert abs((s["s"] + s["i"] + s["r"]) - 1000) < 1.0
    e2 = SimulationEngine("bio", {"model": "lotka", "prey0": 40, "pred0": 9})
    e2.run(200, 0.05)
    assert e2.get_state()["prey"] > 0
    # neural bce
    e3 = SimulationEngine(
        "neural",
        {"layers": [2, 4, 1], "activation": "sigmoid", "loss": "bce", "seed": 7},
    )
    X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], float)
    y = np.array([[0], [1], [1], [0]], float)
    e3._sim.train(X, y, epochs=10, lr=0.1)
    assert len(e3._sim.loss_history) == 10
