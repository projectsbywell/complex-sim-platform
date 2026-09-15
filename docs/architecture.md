# Architecture — complex-sim-platform

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Web UI  │  │ Desktop  │  │ Mobile   │  │  API     │           │
│  │ (React)  │  │  (Tauri) │  │ (Flutter)│  │Client    │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │             │             │              │                 │
├───────┼─────────────┼─────────────┼──────────────┼─────────────────┤
│       ▼             ▼             ▼              ▼                 │
│                   BACKEND LAYER                                     │
│  ┌──────────────────────────────────────────────────────┐          │
│  │              FastAPI Gateway / Router                 │          │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │          │
│  │  │REST API  │ │ WebSocket│ │  Auth    │ │ Rate   │ │          │
│  │  │Endpoints │ │ Handler  │ │  Middle  │ │ Limit  │ │          │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │          │
│  └───────┼────────────┼────────────┼────────────┼────────┘          │
│          │            │            │            │                   │
├──────────┼────────────┼────────────┼────────────┼───────────────────┤
│          ▼            ▼            ▼            ▼                   │
│              SIMULATION CORE LAYER                                │
│  ┌──────────────────────────────────────────────────────┐          │
│  │              simcore.neural                            │          │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │          │
│  │  │ Verlet   │ │ Fluid    │ │Box2D-Lite│ │ MLP/   │ │          │
│  │  │ Integr.  │ │ Stable   │ │Contact   │ │Adam    │ │          │
│  │  │Module    │ │ Fluids   │ │Solver    │ │Module    │ │          │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘ │          │
│  └───────┼────────────┼────────────┼────────────┼────────┘          │
│          │            │            │            │                   │
├──────────┼────────────┼────────────┼────────────┼───────────────────┤
│          ▼            ▼            ▼            ▼                   │
│              DATA LAYER                                         │
│  ┌──────────────────────────────────────────────────────┐          │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        │          │
│  │  │Timescale│ │Redis   │ │Postger│ │Object  │        │          │
│  │  │DB      │ │Cache   │ │SQL    │ │Storage │        │          │
│  │  └────────┘ └────────┘ └────────┘ └────────┘        │          │
│  └──────────────────────────────────────────────────────┘          │
│                                                                     │
│  ┌──────────────────────────────────────────────────────┐          │
│  │              PIPELINE LAYER                           │          │
│  │  Collectors → Batch → Stream → Quality → Train → Infer│         │
│  └──────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer Descriptions

### 1. Client Layer
Handles user interaction through multiple interfaces:
- **Web UI**: React-based real-time visualization dashboard
- **Desktop**: Tauri application for offline/edge scenarios
- **Mobile**: Flutter companion app for remote monitoring
- **API Client**: Direct REST/WS client for programmatic access

**Protocols**: HTTPS (REST), WSS (WebSocket), SSE (Server-Sent Events)

### 2. Backend Layer (FastAPI)
The central orchestration hub:
- **Gateway Router**: Routes all incoming requests to appropriate handlers
- **REST Endpoints**: CRUD operations for simulations, datasets, models
- **WebSocket Handler**: Bidirectional real-time data streaming for live
  simulation state updates and interactive parameter control
- **Auth Middleware**: JWT-based authentication and authorization
- **Rate Limiter**: Token-bucket algorithm protecting against abuse

### 3. Simulation Core Layer (simcore)
Contains all numerical computation modules:
- **Verlet Integrator**: Symplectic integration for particle/rigid body
  dynamics with energy conservation
- **Stable Fluids**: Semi-Lagrangian incompressible Navier-Stokes solver
  (Stam 1999) for real-time fluid simulation
- **Box2D-Lite Contact Solver**: Sequential impulse method for collision
  detection and response
- **MLP/Adam Module**: Feed-forward neural network training with Adam
  optimizer for data-driven simulation augmentation

### 4. Data Layer
Persistent storage infrastructure:
- **TimescaleDB**: Time-series storage for simulation checkpoints,
  telemetry, and metrics (PostgreSQL extension)
- **Redis**: In-memory cache for session state, rate-limiting counters,
  and hot data
- **PostgreSQL**: Relational storage for users, configurations, metadata
- **Object Storage**: S3-compatible storage for simulation artifacts,
  model checkpoints, large datasets (Parquet/HDF5)

### 5. Pipeline Layer
Data lifecycle management:
- **Collectors**: Data ingestion from APIs, CSV files, synthetic streams
- **Batch Processor**: Cleaning, normalization, windowed aggregation
- **Stream Consumer**: Real-time data consumption with ring buffer
- **Quality Module**: Schema validation, outlier detection, reporting
- **Train Module**: Neural network training on collected data
- **Infer Module**: Model inference from trained checkpoints

---

## Interfaces

### Internal Interfaces

**simcore → Backend**:
```python
class SimulationHandle:
    async def start(params: dict) -> SimHandle
    async def step(hid: str, n: int) -> StateUpdate
    async def stop(hid: str) -> FinalState
    async def query(hid: str) -> LiveMetrics
```

**Pipeline → Data Layer**:
```python
class PipelineResult:
    def save_to_timescale(self, table: str) -> None
    def export_parquet(self, path: str) -> None
    def cache_result(self, key: str, ttl: int) -> None
```

**Backend → Pipeline**:
```python
class PipelineRequest:
    source: str  # "api", "csv", "synthetic"
    config: dict
    quality_threshold: float
    train_config: Optional[TrainingConfig]
```

### External Interfaces (REST)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/simulations` | Create new simulation |
| `GET` | `/api/v1/simulations/{id}` | Get simulation state |
| `POST` | `/api/v1/simulations/{id}/start` | Start simulation |
| `POST` | `/api/v1/simulations/{id}/step` | Advance simulation |
| `POST` | `/api/v1/simulations/{id}/stop` | Stop simulation |
| `WS` | `/ws/v1/simulations/{id}` | Real-time state stream |
| `POST` | `/api/v1/pipeline/run` | Execute pipeline |
| `GET` | `/api/v1/pipeline/results/{id}` | Get pipeline results |
| `POST` | `/api/v1/models/train` | Train a model |
| `POST` | `/api/v1/models/infer` | Run inference |
| `GET` | `/api/v1/data/export/{id}` | Export simulation data |

### External Interfaces (WebSocket)

```
Client → Server: {"type": "subscribe", "sim_id": "..."}
Server → Client: {"type": "state", "step": 100, "data": {...}}
Client → Server: {"type": "param_update", "params": {...}}
Server → Client: {"type": "event", "name": "convergence", ...}
```

---

## Data Flow Diagrams

### Simulation Data Flow
```
User Request → Backend Router → simcore.start(params)
    → Simulation Loop (Verlet/Fluid/Box2D)
        → State Update → TimescaleDB (checkpoint)
        → WebSocket → Client (live state)
        → Pipeline (quality, export)
    → Final State → Export (Parquet/JSON)
```

### Training Data Flow
```
Data Collector → Batch (clean, normalize)
    → Quality Report → if quality > threshold:
        → Train Module (MLP + Adam)
            → Checkpoint (JSON) → Model Registry
    → Infer Module → Predictions → Export
```

---

## ADR-001: Use FastAPI over Django for Backend

**Status**: Accepted
**Date**: 2026-09-10
**Deciders**: Worker4, Architecture Team

**Context**: Need a high-performance web framework with async support
for real-time WebSocket streaming of simulation state.

**Decision**: Use FastAPI instead of Django.

**Consequences**:
- Async WebSocket support built-in, critical for real-time sim state
- Automatic OpenAPI docs generation
- Type-safe endpoints via Pydantic models
- Smaller memory footprint per connection
- Tradeoff: No built-in admin interface (we build our own)
- Tradeoff: No ORM (we use asyncpg directly for TimescaleDB)

---

## ADR-002: Use Velocity Verlet over Euler for Integration

**Status**: Accepted
**Date**: 2026-09-10
**Deciders**: Simulation Core Team

**Context**: Need a numerical integrator that preserves energy over
long simulation runs for fluid and particle systems.

**Decision**: Use Velocity Verlet integrator as the default.

**Consequences**:
- Symplectic integration guarantees bounded energy drift
- Second-order accuracy (O(dt²)) vs Euler's O(dt)
- 2x computation cost per step
- Standard in molecular dynamics and physics engines
- Tradeoff: More complex to implement than Euler (requires storing
  previous acceleration)

---

## ADR-003: Use TimescaleDB over InfluxDB for Time-Series Storage

**Status**: Accepted
**Date**: 2026-09-10
**Deciders**: Data Layer Team

**Context**: Need a time-series database for storing simulation
checkpoints, metrics, and telemetry data.

**Decision**: Use TimescaleDB (PostgreSQL extension) over InfluxDB.

**Consequences**:
- Full SQL support enables complex analytical queries
- PostgreSQL ecosystem provides robust tooling
- Native continuous aggregates for efficient downsampling
- Joins with relational data (users, configurations)
- Tradeoff: Higher resource usage than InfluxDB for pure time-series
- Tradeoff: Setup more complex (PostgreSQL dependency)

---

## ADR-004: Use Parquet for Batch Pipeline Output

**Status**: Accepted
**Date**: 2026-09-10
**Deciders**: Pipeline Team

**Context**: Need efficient columnar storage for pipeline batch
processing results that integrates with the broader data ecosystem.

**Decision**: Use Apache Parquet as primary batch output format.

**Consequences**:
- Excellent compression ratios (5-10x)
- Columnar access enables fast projections (read only needed columns)
- Native Arrow compatibility for zero-copy reads
- Ecosystem integration (Spark, Dask, pandas)
- Tradeoff: Not designed for streaming writes
- Tradeoff: No partial row access (use HDF5 for that)

---

## ADR-005: Use JSON for Model Checkpoints

**Status**: Accepted
**Date**: 2026-09-10
**Deciders**: ML/Training Team

**Context**: Need a portable checkpoint format for trained neural
network models that is human-readable and easy to version.

**Decision**: Store model weights as JSON arrays.

**Consequences**:
- Human-readable, diff-friendly checkpoints
- Portable across platforms (no pickle security issues)
- Easy to integrate with git for model versioning
- Tradeoff: Larger file size than binary formats
- Tradeoff: Slower load times than binary checkpoints
- Mitigation: Use gzip compression for production checkpoints

---

## ADR-006: Use Semi-Implicit Euler over Velocity Verlet for Particles

**Status**: Accepted (implementation diverges from ADR-002)
**Date**: 2026-09-15
**Deciders**: Simulation Core Team (Worker4)

**Context**: ADR-002 specified Velocity Verlet integration for energy
conservation. However, implementation in `particles.py` uses
**semi-implicit Euler** (symplectic Euler):
```python
v(t+dt) = v(t) + a(t) * dt
x(t+dt) = x(t) + v(t+dt) * dt
```
This differs from Velocity Verlet:
```python
x(t+dt) = x(t) + v(t)*dt + 0.5*a(t)*dt²
v(t+dt) = v(t) + 0.5*(a(t) + a(t+dt))*dt
```

**Decision**: Accept semi-implicit Euler as the implementation for
particle and physics modules. Retain Velocity Verlet as the documented
goal for future v1.1 refactoring.

**Consequences**:
- Semi-implicit Euler is symplectic (like Verlet) — bounded energy drift
- Simpler implementation, less computation per step
- First-order vs second-order — acceptable for interactive simulations
- Velocity Verlet to be implemented in v1.1 with adaptive time-stepping
- All documentation updated to reflect actual implementation
- `docs/PERFORMANCE.md` and `docs/RESEARCH.md` note the divergence

---

## ADR-007: Use Jacobi Iteration for Pressure Solve (Not Gauss-Seidel)

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Simulation Core Team

**Context**: Stable Fluids pressure projection requires solving the
Poisson equation. Stam's original paper uses Gauss-Seidel.

**Decision**: Use Jacobi iteration for parallelizability, with
configurable `pressure_iters` parameter (default 20).

**Consequences**:
- Jacobi is embarrassingly parallel (unlike Gauss-Seidel)
- Converges at similar rate but each iteration is independent
- Configurable iteration count allows real-time/accuracy tradeoff
- Vectorized NumPy implementation achieves ~360 steps/s at 32²


---