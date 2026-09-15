# Module: simcore — Simulation Core

The `simcore` package contains all numerical simulation engines:
particle dynamics, fluid simulation, rigid body contact, neural
network augmentation, and biological models.

## Package Structure

```
simcore/
├── __init__.py        # Public API (version + re-exports)
├── base.py            # Simulatable ABC, Vec2, seed_rng, clamp
├── particles.py       # N-body 2-D particle sim (semi-implicit Euler + spatial hash)
├── fluids.py          # Stable Fluids 2-D (Stam 1999): Gauss-Seidel diffusion +
│                      # semi-Lagrangian advection + Jacobi pressure projection
├── physics.py         # 2-D rigid body sim (circle colliders, impulse-based contact)
├── neural.py          # MLP with Adam optimizer (pure NumPy)
├── bio.py             # SIR (Kermack-McKendrick), Lotka-Volterra, Ecosystem grid
├── engine.py          # SimulationEngine facade (uniform API across all models)
├── state.py           # State serialisation: JSON, CSV helpers
└── export.py          # Multi-format export: CSV, JSON, Parquet, HDF5 (with fallbacks)
```

## Module: base.py

Abstract base class and numeric utilities shared by all simulation modules.

```python
from simcore.base import Simulatable, Vec2, seed_rng, clamp

class Simulatable(abc.ABC):
    """Interface every simulation module must satisfy."""
    def step(self, dt: float) -> None: ...
    def get_state(self) -> Dict[str, Any]: ...
    def set_state(self, d: Dict[str, Any]) -> None: ...
    def get_params(self) -> Dict[str, Any]: ...
    def set_params(self, p: Dict[str, Any]) -> None: ...

def seed_rng(seed: Optional[int]) -> np.random.Generator:
    """Return deterministic NumPy Generator. Uses np.random.default_rng(seed)."""

class Vec2:
    """Minimal 2-D vector with +, -, *, dot, length, normalized."""
```

## Module: particles.py

N-body 2-D particle simulation with spatial-hash collision detection.

**Integration**: Semi-implicit Euler (symplectic Euler) — not Velocity Verlet.
The integrator updates velocity first, then position:
```python
self._vy += gravity * dt  # update velocity
self._x += self._vx * dt  # then update position
```
This provides symplectic-like energy behavior with lower cost than Velocity Verlet.

```python
from simcore.particles import ParticleSimulation

sim = ParticleSimulation(params={"n": 200, "gravity": 9.81, "damping": 0.999})
sim.step(dt=0.001)
state = sim.get_state()
```

### API Reference

```python
class ParticleSimulation:
    def __init__(self, params: Optional[Dict[str, Any]] = None)
    def step(self, dt: float) -> None
    def get_state(self) -> Dict[str, Any]
    def set_state(self, d: Dict[str, Any]) -> None
    def get_params(self) -> Dict[str, Any]
    def set_params(self, p: Dict[str, Any]) -> None
```

## Module: fluids.py

Semi-Lagrangian incompressible Navier-Stokes solver based on
Stam (1999) "Stable Fluids".

**Pipeline per step**: Diffusion (Gauss-Seidel) → Advection (semi-Lagrangian,
vectorized NumPy) → Projection (Jacobi pressure solve, `pressure_iters` configurable).

```python
from simcore.fluids import FluidSimulation

sim = FluidSimulation(params={"size": 128, "viscosity": 1e-4, "pressure_iters": 20})
sim.step(dt=0.016)
state = sim.get_state()
```

### API Reference

```python
class FluidSimulation:
    def __init__(self, params: Optional[Dict[str, Any]] = None)
    def add_density(self, x: int, y: int, amount: float) -> None
    def add_velocity(self, x: int, y: int, vx: float, vy: float) -> None
    def step(self, dt: float) -> None
    def get_state(self) -> Dict[str, Any]
    def set_state(self, d: Dict[str, Any]) -> None
    def get_params(self) -> Dict[str, Any]
    def set_params(self, p: Dict[str, Any]) -> None
```

Key implementation details:
- `_diffuse()`: Gauss-Seidel relaxation (4 iterations, stable implicit solve)
- `_advect()`: Semi-Lagrangian with bilinear interpolation, fully vectorized via NumPy meshgrid
- `_pressure_jacobi()`: Jacobi iteration solving ∇²p = -div(v)
- `_set_boundary()`: Reflective boundary conditions for velocity components

## Module: physics.py

2-D rigid body simulation with circle colliders and impulse-based
collision resolution (sequential impulse method, Box2D-lite style).

**Contact solver**: Iterates over all body pairs (O(n²) brute-force, fine for n << 1000).
Impulse formula: `j = (1 + e) * dvn / (1/m_a + 1/m_b)`

```python
from simcore.physics import PhysicsSimulation

sim = PhysicsSimulation(params={"n": 20, "restitution": 0.6, "friction": 0.3})
sim.step(dt=0.001)
state = sim.get_state()
```

### API Reference

```python
class PhysicsSimulation:
    def __init__(self, params: Optional[Dict[str, Any]] = None)
    def step(self, dt: float) -> None
    def get_state(self) -> Dict[str, Any]
    def set_state(self, d: Dict[str, Any]) -> None
    def get_params(self) -> Dict[str, Any]
    def set_params(self, p: Dict[str, Any]) -> None
```

## Module: neural.py

MLP with Adam optimizer for data-driven simulation augmentation.
Pure NumPy implementation — no ML framework dependency.

**Architecture**: Fully-connected feed-forward with configurable layers.
He initialization for ReLU, Xavier for sigmoid/tanh.

**Adam**: β₁=0.9, β₂=0.999, ε=1e-8 with bias correction.
Losses: MSE (regression) and BCE (classification).

```python
from simcore.neural import NeuralSimulation

sim = NeuralSimulation(params={"layers": [10, 128, 64, 32, 2],
                                "activation": "relu", "optimiser": "adam"})
sim.train(X, y, epochs=200, lr=0.001)
predictions = sim.predict(X_test)
```

### API Reference

```python
class NeuralSimulation:
    def __init__(self, params: Optional[Dict[str, Any]] = None)
    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 100, lr: float = 0.01) -> List[float]
    def predict(self, X: np.ndarray) -> np.ndarray
    def get_state(self) -> Dict[str, Any]
    def set_state(self, d: Dict[str, Any]) -> None
    def get_params(self) -> Dict[str, Any]
    def set_params(self, p: Dict[str, Any]) -> None
    @property
    def loss_history(self) -> List[float]
```

## Module: bio.py

Biological/ecological simulation models: SIR (Kermack-McKendrick),
Lotka-Volterra predator-prey, and Ecosystem grid.

```python
from simcore.bio import BioSimulation

# SIR model
sim = BioSimulation(params={"model": "sir", "n_pop": 10000, "beta": 0.3, "gamma": 0.1})
sim.step(dt=0.1)

# Lotka-Volterra
sim = BioSimulation(params={"model": "lotka", "prey0": 40.0, "pred0": 9.0})
```

### API Reference

```python
class BioSimulation:
    def __init__(self, params: Optional[Dict[str, Any]] = None)
    def step(self, dt: float) -> None
    def get_state(self) -> Dict[str, Any]
    def set_state(self, d: Dict[str, Any]) -> None
    def get_params(self) -> Dict[str, Any]
    def set_params(self, p: Dict[str, Any]) -> None
```

Internal models:
- `_SIR`: Euler integration of Kermack-McKendrick ODEs
- `_LotkaVolterra`: Euler integration of predator-prey ODEs
- `_Ecosystem`: Grid-based cellular automaton with vegetation/herbivore/carnivore

## Module: engine.py

`SimulationEngine` facade providing a uniform API across all simulation models.

```python
from simcore.engine import SimulationEngine

engine = SimulationEngine("fluids", params={"size": 128})
engine.step(dt=0.016)
state = engine.get_state()
engine.set_state(state)
```

### API Reference

```python
class SimulationEngine:
    def __init__(self, kind: str, params: Optional[Dict[str, Any]] = None)
    def step(self, dt: float) -> None
    def run(self, steps: int, dt: float) -> None
    def get_state(self) -> Dict[str, Any]
    def set_state(self, d: Dict[str, Any]) -> None
    def get_params(self) -> Dict[str, Any]
    def set_params(self, p: Dict[str, Any]) -> None
    def to_json(self, indent: int = 2) -> str
```

Valid `kind` values: `"particles"`, `"fluids"`, `"physics"`, `"neural"`, `"bio"`.

## Module: state.py

State serialisation helpers for persisting simulation state to disk.

```python
from simcore.state import to_json_str, save_json, load_json, to_csv
```

## Module: export.py

Multi-format state export supporting CSV, JSON, Parquet, and HDF5.
Graceful fallbacks if optional libraries (pandas/pyarrow, h5py) are absent.

```python
from simcore.export import export_csv, export_json, export_parquet, export_hdf5
```

## Shared Utilities: base.py

```python
from simcore.base import seed_rng, clamp, Vec2

rng = seed_rng(42)          # Deterministic Generator (np.random.default_rng)
x = clamp(15.0, 0.0, 10.0)  # → 10.0
v = Vec2(3.0, 4.0)          # 2-D vector arithmetic
```
