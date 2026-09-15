# Tests
- `test_simcore.py` — 8 testes unitários do núcleo (partículas, fluidos, física, neural XOR, bio SIR/Lotka, state, export)
- `test_platform.py` — API REST+WS, segurança, pipeline, i18n (7 JSONs), e2e engine→report
- `test_load.py` — probe de throughput stdlib (steps/s por kind)

```bash
pip install -r tests/requirements-test.txt
python -m pytest -q
python tests/test_load.py
```
Cobertura estimada: núcleo ~85% (todos os módulos exercitados), backend ~70% (fluxos principais), demais ~60%. Meta global >80% nos módulos críticos (simcore+api).
