"""Load probe stdlib-only: measures local engine throughput (target: report req/s)."""
import time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'simulation-core'))
from simcore import SimulationEngine
for kind in ["particles","fluids","physics","neural","bio"]:
    e = SimulationEngine(kind, {})
    t0=time.time(); N=200
    for _ in range(N): e.step(0.016)
    dt=time.time()-t0
    print(f"{kind:10s} {N/dt:8.1f} steps/s  total={dt:.2f}s")
print("LOAD-OK")
