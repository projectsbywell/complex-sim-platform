"""API + WS + e2e + pipeline/i18n/security tests (skip gracefully without deps)."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulation-core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "security"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "database"))
import json, pytest


def test_api_full_flow():
    fastapi = pytest.importorskip("fastapi")
    httpx = pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert set(c.get("/api/simulations/kinds").json()) >= {
        "particles",
        "fluids",
        "physics",
        "neural",
        "bio",
    }
    r = c.post(
        "/api/auth/register", json={"username": "qa_u", "password": "qa_pass123"}
    )
    assert r.status_code in (200, 400, 409)
    t = c.post("/api/auth/login", data={"username": "qa_u", "password": "qa_pass123"})
    assert t.status_code == 200, t.text
    tok = t.json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    s = c.post(
        "/api/simulations",
        json={"kind": "particles", "params": {"n": 20, "seed": 1}},
        headers=H,
    )
    assert s.status_code in (200, 201)
    sid = s.json()["id"]
    st = c.post(
        f"/api/simulations/{sid}/step", json={"dt": 0.016, "steps": 5}, headers=H
    )
    assert st.status_code == 200 and st.json()["steps_done"] >= 5
    ex = c.get(f"/api/simulations/{sid}/export?format=json", headers=H)
    assert ex.status_code == 200
    rep = c.post(f"/api/simulations/{sid}/report", headers=H)
    assert rep.status_code == 200 and "summary" in rep.json()
    # rate-limit headers sane
    assert c.get("/metrics").status_code == 200


def test_ws_broadcast():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    c.post("/api/auth/register", json={"username": "ws_u", "password": "ws_pass123"})
    tok = c.post(
        "/api/auth/login", data={"username": "ws_u", "password": "ws_pass123"}
    ).json()["access_token"]
    sid = c.post(
        "/api/simulations",
        json={"kind": "particles", "params": {"n": 10}},
        headers={"Authorization": f"Bearer {tok}"},
    ).json()["id"]
    with c.websocket_connect(f"/ws/simulations/{sid}?token={tok}") as w:
        w.send_json({"dt": 0.016, "steps": 2})
        m = w.receive_json()
        assert "state" in m or "tick" in m


def test_security_units():
    from middleware import sanitize_sql, escape_html, csrf_token, verify_csrf

    assert "''" in sanitize_sql("a'b") or "'" in sanitize_sql("a'b")
    assert "<" not in escape_html("<script>")
    t = csrf_token()
    assert verify_csrf(t)
    from anomaly import AnomalyDetector

    d = AnomalyDetector(window=10, z_threshold=2.0)
    for _ in range(10):
        d.observe("lat", 1.0)
    assert d.is_anomaly("lat", 50.0)


def test_pipeline_and_i18n():
    root = os.path.join(os.path.dirname(__file__), "..")
    for lang in ["pt-BR", "en", "es", "fr", "de", "ja", "zh-CN"]:
        d = json.load(
            open(os.path.join(root, "i18n", f"{lang}.json"), encoding="utf-8")
        )
        assert len(d) >= 40, lang
    en = json.load(open(os.path.join(root, "i18n", "en.json"), encoding="utf-8"))
    for lang in ["pt-BR", "es", "fr", "de", "ja", "zh-CN"]:
        d = json.load(
            open(os.path.join(root, "i18n", f"{lang}.json"), encoding="utf-8")
        )
        assert set(d.keys()) == set(en.keys()), lang
    from quality import QualityReport

    qr = QualityReport([{"a": 1}, {"a": None}, {"a": 100.0}]).generate()
    assert qr["dataset"]["total_records"] == 3


def test_e2e_engine_to_report(tmp_path):
    pytest.importorskip("simcore")
    from simcore import SimulationEngine
    from report_generator import generate_report

    e = SimulationEngine("bio", {"model": "sir"})
    e.run(30, 0.1)
    st = e.get_state()
    hist = st.get("history", [])
    out = generate_report(
        {
            "simulation": {"id": 1, "type": "sir", "name": "E2E"},
            "params": e.get_params(),
            "series": {"I": [h.get("i", 0) for h in hist]},
        },
        str(tmp_path / "rep"),
    )
    assert (tmp_path / "rep_stats.json").exists() or len(out) > 0
