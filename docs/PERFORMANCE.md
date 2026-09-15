# Performance

## Benchmarks (dev, CPU — pós-correção v1.1)
| kind | steps/s | gargalo |
|---|---|---|
| particles (200) | ~2.3k | colisão O(n²) → spatial hash |
| fluids (32²) | ~360 (era 29) | advecção vetorizada 12.5×; `pressure_iters` ajustável (20→8 em realtime) |
| physics (12) | ~22k | impulso é O(n²) pequeno |
| neural | treino XOR 400ep <2s | vectorizado numpy |
| bio | ~800k+ | ODE puro |

Correção v1.1: `_advect` de loop Python → NumPy vetorizado (meshgrid + indexação avançada, matemática idêntica); novo param `pressure_iters`.

## Profiling
```bash
python -m cProfile -o prof.out simulation-core/example_run.py
python -c "import pstats; pstats.Stats('prof.out').sort_stats('cumulative').print_stats(15)"
```
## Checklist
- [x] seeds determinísticas
- [x] spatial hash em partículas/física
- [x] cache LRU no backend (60s)
- [x] rate-limit 100/min
- [ ] numba/JAX se grade >64² (roadmap)
