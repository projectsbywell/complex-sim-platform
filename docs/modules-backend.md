# Module: backend — API Server

The `backend` package provides the FastAPI-based REST and WebSocket
server that orchestrates all simulation and pipeline operations.

## Package Structure

```
backend/
├── main.py              # Application entry point
├── app/
│   ├── __init__.py
│   ├── router.py        # Main route definitions
│   ├── api/
│   │   ├── simulations.py
│   │   ├── pipeline.py
│   │   ├── models.py
│   │   └── data.py
│   ├── ws/
│   │   ├── manager.py   # WebSocket connection manager
│   │   └── handlers.py  # WS message handlers
│   ├── middleware/
│   │   ├── auth.py      # JWT authentication
│   │   ├── rate_limit.py
│   │   └── cors.py
│   ├── schemas/
│   │   ├── simulation.py
│   │   ├── pipeline.py
│   │   └── models.py
│   └── dependencies.py
├── config.py            # Pydantic settings
└── security/
    ├── auth.py
    ├── permissions.py
    └── tokens.py
```

## Module: main.py

```python
from backend.main import create_app, start_background_tasks

app = create_app(config=AppConfig(
    host="0.0.0.0",
    port=8000,
    debug=False,
    cors_origins=["http://localhost:3000"],
    rate_limit="100/minute",
))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Module: app/router.py

Central route definitions with versioning:

```python
from backend.router import api_router, ws_router

app.include_router(api_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/ws/v1")
```

## REST API Endpoints

### Simulations

```python
# Create simulation
POST /api/v1/simulations
{
    "name": "fluid-cavity",
    "type": "fluid",
    "parameters": {
        "resolution": 256,
        "viscosity": 0.1,
        "dt": 0.016
    },
    "initial_conditions": {
        "velocity_field": "zeros",
        "density": {"center": [128, 128], "radius": 20, "value": 1.0}
    }
}
# Returns: {"simulation_id": "sim_abc123", "status": "created"}

# Get simulation state
GET /api/v1/simulations/{simulation_id}
# Returns: {"id": "...", "step": 1000, "state": {...}, "metrics": {...}}

# Start simulation
POST /api/v1/simulations/{simulation_id}/start
# Returns: {"status": "running", "estimated_steps": 10000}

# Step simulation
POST /api/v1/simulations/{simulation_id}/step
{"n_steps": 10}
# Returns: {"step": 1010, "state_update": {...}}

# Stop simulation
POST /api/v1/simulations/{simulation_id}/stop
# Returns: {"status": "stopped", "final_state": {...}}
```

### Pipeline

```python
# Run pipeline
POST /api/v1/pipeline/run
{
    "source": "synthetic",
    "source_config": {"schema": {"x": "float", "y": "float"}},
    "quality_threshold": 0.8,
    "train_config": {
        "epochs": 50,
        "learning_rate": 0.001,
        "hidden_layers": [64, 32]
    }
}
# Returns: {"pipeline_id": "pl_xyz", "status": "running"}

# Get pipeline results
GET /api/v1/pipeline/results/{pipeline_id}
# Returns: {"quality_score": 0.92, "model_metrics": {...}, "data_summary": {...}}
```

### Models

```python
# Train a model
POST /api/v1/models/train
{
    "dataset_id": "ds_abc",
    "config": {
        "hidden_layers": [128, 64],
        "epochs": 100,
        "optimizer": "adam"
    }
}
# Returns: {"model_id": "model_123", "status": "training"}

# Run inference
POST /api/v1/models/infer
{
    "model_id": "model_123",
    "checkpoint": "path/to/checkpoint.json",
    "data": [[...], [...]]
}
# Returns: {"predictions": [...], "confidence": [...]}
```

### Data Export

```python
# Export simulation data
GET /api/v1/data/export/{simulation_id}?format=parquet
# Returns: File download (Parquet format)
```

## WebSocket Handler

```python
from backend.ws.manager import WSManager

ws_manager = WSManager()

async def simulation_ws(websocket, simulation_id: str):
    await ws_manager.connect(websocket, simulation_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data["type"] == "param_update":
                # Update simulation parameters in real-time
                await update_params(simulation_id, data["params"])
            elif data["type"] == "request_state":
                state = await get_state(simulation_id)
                await websocket.send_json({"type": "state", **state})
    finally:
        await ws_manager.disconnect(websocket, simulation_id)
```

### WebSocket Message Protocol

```json
// Client → Server: Subscribe to simulation
{"type": "subscribe", "sim_id": "sim_abc123", "channels": ["state", "events"]}

// Server → Client: Live state update
{"type": "state", "sim_id": "sim_abc123", "step": 1500,
 "metrics": {"energy": 0.95, "fps": 60}, "data": {...}}

// Client → Server: Parameter update
{"type": "param_update", "sim_id": "sim_abc123", "params": {"viscosity": 0.2}}

// Server → Client: Event notification
{"type": "event", "sim_id": "sim_abc123", "name": "convergence",
 "message": "Simulation converged at step 5000"}
```

## Middleware Stack

```python
# Order matters: applied top-to-bottom
app.add_middleware(CORSMiddleware, origins=[...])
app.add_middleware(RateLimitMiddleware, limits={...})
app.add_middleware(AuthMiddleware, jwt_secret=...)
app.add_middleware(JSONLoggingMiddleware)
```

## Configuration

```python
from backend.config import AppConfig, settings

class AppConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = "postgresql://localhost/sim"
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "change-me"
    rate_limit: str = "100/minute"
    cors_origins: List[str] = ["http://localhost:3000"]
    checkpoint_dir: str = "./checkpoints"

settings = AppConfig()
```
