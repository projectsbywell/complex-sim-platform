# FAQ — complex-sim-platform

**Perguntas Frequentes**

---

**1. What is complex-sim-platform?**
A simulation platform for complex systems including particle dynamics,
fluid simulation, epidemiological modeling, and neural network training.

**2. What programming language is it written in?**
Python 3.10+ with NumPy as the core numerical library. The backend
uses FastAPI and the frontend is a React application.

**3. How do I install the platform?**
```bash
pip install -r pipeline/requirements.txt
pip install -e .
```

**4. What is the minimum Python version?**
Python 3.10. Earlier versions are not supported.

**5. Do I need a GPU?**
No. The platform runs on CPU with NumPy. GPU acceleration via JAX
is optional for differentiable physics and large-scale training.

**6. How do I start the backend server?**
```bash
python backend/main.py
```
The server starts on `http://localhost:8000`.

**7. What simulation types are available?**
Particle systems (Verlet integrator), fluid simulation (Stable Fluids),
rigid body contact (Box2D-lite), and neural network models (MLP/Adam).

**8. How do I run a simulation?**
Create a simulation via `POST /api/v1/simulations`, then start it
with `POST /api/v1/simulations/{id}/start`.

**9. How does WebSocket streaming work?**
Connect to `ws://localhost:8000/ws/v1/simulations/{id}`. Subscribe
to channels and receive real-time state updates.

**10. What data formats are supported?**
JSON for API requests/responses, Parquet for batch pipeline output,
HDF5 for large simulation snapshots, and CSV for data import.

**11. How do I ensure deterministic simulations?**
Use `set_seed(42)` before running simulations. The platform uses
`numpy.random.default_rng(seed)` for all stochastic components.

**12. What is the maximum simulation size?**
Depends on available memory. Particle systems scale as O(n²) for
naive force computation. Fluid simulation scales as O(resolution²).
Typical limits: 100k particles, 512×512 fluid grid.

**13. How do I add a custom simulation type?**
Implement a new module in `simcore/` following the existing interface
patterns. Register it in `simcore/__init__.py`. Add tests in `tests/`.

**14. Can I use the platform in production?**
Yes. Docker deployment is supported. See `docs/tutorials.md` for
the deployment tutorial. Use TimescaleDB and Redis for production data
infrastructure.

**15. What about data privacy and security?**
See `docs/SECURITY.md` for the security architecture overview.
The platform supports TLS, authentication, rate limiting, and input
sanitization out of the box.

**16. How do I contribute to the project?**
See `docs/CONTRIBUTING.md` for the full contributing guide including
branch naming, commit conventions, and code review process.

**17. What is the quality score in reports?**
A 0-100 metric combining missing data rate, outlier rate, and
schema validity. A score above 70 indicates usable data quality.

**18. How do I train a model?**
Use the pipeline: collect data, call `PipelineTrainer.train()`,
and save checkpoints. See Tutorial 3 in `docs/tutorials.md`.

**19. What are the performance characteristics?**
Particle simulation: ~10k particles at 60fps (CPU). Fluid: 256×256
at 60fps (CPU). Training depends on model size and data volume.

**20. Where do I get help?**
Check the documentation, file an issue on GitHub, or ask in the
project discussions. The RESEARCH.md file contains all references
and background material.
