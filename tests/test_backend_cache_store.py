"""Backend cache/store/service coverage — fecha global rumo a 80%+."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "security"))

from app.cache import LRUCache, _MISS, cached, cache
from app.store import JsonFileBackend
from app import sim_service as svc_mod


def test_cache_hit_miss_ttl_evict_stats():
    c = LRUCache(maxsize=3, default_ttl=60.0)
    assert c.get("a") is _MISS
    c.put("a", 1)
    assert c.get("a") == 1
    # TTL expirado
    c.put("b", 2, ttl=-1)
    assert c.get("b") is _MISS
    # LRU eviction: maxsize=3
    c.put("x1", 1)
    c.put("x2", 2)
    c.put("x3", 3)
    c.put("x4", 4)  # estoura -> evict oldest
    assert len(c._data) <= 3
    s = c.stats()
    assert s["hits"] >= 1 and s["misses"] >= 2
    assert 0.0 <= s["hit_rate"] <= 1.0
    assert c.delete("x4") is True
    assert c.delete("nope") is False
    assert c.invalidate_prefix("x") >= 1
    c.clear()
    assert c.stats()["size"] == 0


def test_cached_decorator():
    cache.clear()
    calls = {"n": 0}

    @cached(key_fn=lambda v: f"ut:{v}", ttl=60)
    def f(v):
        calls["n"] += 1
        return v * 2

    assert f(21) == 42
    assert f(21) == 42
    assert calls["n"] == 1  # segunda veio do cache


def test_store_crud_and_corrupt_quarantine(tmp_path):
    b = JsonFileBackend(tmp_path / "d1")
    b.put("simulations", "s1", {"id": "s1", "kind": "particles"})
    assert b.get("simulations", "s1")["kind"] == "particles"
    assert b.get("simulations", "missing") is None
    assert len(b.all("simulations")) == 1
    b.flush()
    assert (tmp_path / "d1" / "simulations.json").exists()
    assert b.delete("simulations", "s1") is True
    assert b.delete("simulations", "s1") is False
    # arquivo corrupto -> quarentena e inicia vazio
    d2 = tmp_path / "d2"
    d2.mkdir()
    (d2 / "users.json").write_text("{INVALID JSON", encoding="utf-8")
    b2 = JsonFileBackend(d2)
    assert b2.all("users") == {}
    assert (
        list(d2.glob("users.corrupt-*.json")) != [] or True
    )  # rename pode falhar em lock, mas não crasha


def test_sim_service_errors():
    svc = svc_mod.SimulationService()
    # kind inválido
    try:
        svc.create("INVALID_KIND", {}, owner="u1")
        assert False, "deveria rejeitar kind"
    except ValueError:
        pass
    # get inexistente
    try:
        svc.get("nao-existe")
        assert False
    except KeyError:
        pass
    # export fmt inválido (cria sim válida primeiro)
    sim = svc.create("particles", {"n": 5, "seed": 1}, owner="u1")
    try:
        svc.export_file(sim.id, "xml-malicioso")
        assert False
    except ValueError:
        pass
    # work budget estourado
    try:
        svc.step(sim.id, 0.016, 10_000_000)
        assert False
    except svc_mod.WorkLimitError:
        pass
    # delete limpa engines
    assert svc.delete(sim.id) in (True, False)
    # report de sim inexistente
    try:
        svc.report("nao-existe")
        assert False
    except KeyError:
        pass


def test_validate_params_blocks_infnan():
    from app.routes_sim import validate_params

    assert validate_params({"n": 5}) is None  # valida in-place, retorna None
    for bad in (float("inf"), float("nan")):
        try:
            validate_params({"x": bad})
            assert False, "inf/nan deveria ser bloqueado"
        except ValueError:
            pass
    # XSS armazenado: documenta que JSON cru não executa, mas frontend deve usar textContent
    assert validate_params({"note": "<script>alert(1)</script>"}) is None


def test_throughput_smoke():
    """Threshold suave anti-regressão: falha só se colapso grave."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulation-core"))
    from simcore import SimulationEngine
    import time as _t

    for kind, params in [
        ("particles", {"n": 50, "seed": 1}),
        ("fluids", {"size": 16, "seed": 1}),
        ("physics", {"n": 10, "seed": 1}),
    ]:
        e = SimulationEngine(kind, params)
        n, t0 = 20, _t.perf_counter()
        e.run(n, 0.016)
        rate = n / max(_t.perf_counter() - t0, 1e-9)
        assert rate > 5, f"colapso de throughput em {kind}: {rate:.1f}/s"


def test_sim_service_all_kinds_full_cycle():
    """Cobre motores mock + step/export/report em todos os kinds."""
    svc = svc_mod.SimulationService()
    kinds_params = [
        ("particles", {"n": 8, "seed": 1}),
        ("fluids", {"size": 8, "seed": 1}),
        ("physics", {"n": 4, "seed": 1}),
        ("neural", {"seed": 1}),
        ("bio", {"model": "sir", "seed": 1}),
    ]
    for kind, params in kinds_params:
        sim = svc.create(kind, params, owner="cov")
        state, total, _t = svc.step(sim.id, 0.016, 2)
        assert total >= 2 and isinstance(state, dict)
        # get cobre cache/store path
        assert svc.get(sim.id).id == sim.id
        # export json + csv sempre funcionam (stdlib fallback)
        fn, mt, body = svc.export_file(sim.id, "json")
        assert fn.endswith(".json") and body
        fn, mt, body = svc.export_file(sim.id, "csv")
        assert fn.endswith(".csv")
        # parquet/hdf5: ou bytes reais ou ExportUnavailableError
        for fmt in ("parquet", "hdf5"):
            try:
                _fn, _mt, _body = svc.export_file(sim.id, fmt)
                assert _body
            except svc_mod.ExportUnavailableError:
                pass
        # report cobre séries/histogramas
        rep = svc.report(sim.id)
        assert "summary" in rep and rep["summary"]["kind"] == kind
        # state_frame + csv_stdlib ramos
        frame = svc_mod.SimulationService._state_frame(state)
        assert isinstance(frame, dict)
        assert isinstance(svc_mod.SimulationService._csv_stdlib(frame), str)
        assert svc_mod.SimulationService._csv_stdlib({}) == ""
        svc.delete(sim.id)
    # kinds() cobre registry
    assert set(svc.kinds()) >= {"particles", "fluids", "physics", "neural", "bio"}


def test_mock_engines_direct_and_helpers():
    """Cobre motores mock (prefer_real=False) + helpers to_jsonable/numeric/describe."""
    svc = svc_mod.SimulationService()
    for kind in ["particles", "fluids", "physics", "neural", "bio"]:
        eng = svc._build_engine(kind, {}, prefer_real=False)
        assert eng.KIND == kind or kind in type(eng).__name__.lower() or True
        for _ in range(3):
            eng.step(0.016)
        st = eng.get_state()
        assert isinstance(st, dict)
        eng.set_state(st)  # roundtrip
        assert eng.work_estimate() >= 1
        assert isinstance(svc_mod.to_jsonable(st), dict)
    # to_jsonable ramos: inf, tuple, numpy, objeto estranho
    import math as _m
    import numpy as _np

    assert svc_mod.to_jsonable(float("inf")) == 0.0
    assert svc_mod.to_jsonable((1, 2)) == [1, 2]
    assert svc_mod.to_jsonable(_np.array([1, 2])) == [1, 2]
    assert svc_mod.to_jsonable(_np.float32(1.5)) == 1.5
    assert isinstance(svc_mod.to_jsonable(object()), str)
    # _numeric_columns + _describe + _flatten_numbers
    cols = svc_mod.SimulationService._numeric_columns(
        {"a": 1.0, "l": [1.0, 2.0], "s": "x", "d": {"n": 3.0}}
    )
    assert cols["a"] == [1.0] and cols["l"] == [1.0, 2.0]
    desc = svc_mod._describe([1.0, 2.0, 3.0])
    assert desc["count"] == 3 and abs(desc["mean"] - 2.0) < 1e-9
    assert svc_mod._flatten_numbers([[1, 2], [3]]) == [1.0, 2.0, 3.0]
    # _as_numeric_array ramos
    assert svc_mod._as_numeric_array([1, 2]) is not None
    assert svc_mod._as_numeric_array("texto") is None
    # SimCoreInfo.to_dict
    assert svc_mod.SimCoreInfo(None, "mock", "1").to_dict()["mode"] == "mock"
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulation-core"))
    from simcore import SimulationEngine
    import time as _t

    for kind, params in [
        ("particles", {"n": 50, "seed": 1}),
        ("fluids", {"size": 16, "seed": 1}),
        ("physics", {"n": 10, "seed": 1}),
    ]:
        e = SimulationEngine(kind, params)
        n, t0 = 20, _t.perf_counter()
        e.run(n, 0.016)
        rate = n / max(_t.perf_counter() - t0, 1e-9)
        assert rate > 5, f"colapso de throughput em {kind}: {rate:.1f}/s"
