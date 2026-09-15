# Tutorials — complex-sim-platform

Step-by-step guides covering the full range of platform capabilities.

---

## Tutorial 1: Your First Simulation

**Objective**: Run a simple particle simulation from start to finish.

### Step 1: Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install platform
cd complex-sim-platform
pip install -r pipeline/requirements.txt
pip install -e .
```

### Step 2: Start the Backend Server

```bash
python backend/main.py
# Server starts on http://localhost:8000
```

### Step 3: Create a Simulation via API

```bash
curl -X POST http://localhost:8000/api/v1/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "particle-bounce",
    "type": "particle",
    "parameters": {
      "n_particles": 500,
      "dt": 0.001,
      "damping": 0.99,
      "bounds": [0, 0, 100, 100]
    },
    "initial_conditions": {
      "velocity_distribution": "gaussian",
      "seed": 42
    }
  }'
```

Response: `{"simulation_id": "sim_abc123", "status": "created"}`

### Step 4: Start the Simulation

```bash
curl -X POST http://localhost:8000/api/v1/simulations/sim_abc123/start
```

### Step 5: Step Forward

```bash
curl -X POST http://localhost:8000/api/v1/simulations/sim_abc123/step \
  -H "Content-Type: application/json" \
  -d '{"n_steps": 100}'
```

### Step 6: Check State

```bash
curl http://localhost:8000/api/v1/simulations/sim_abc123
```

### Step 7: Stop and Export

```bash
curl -X POST http://localhost:8000/api/v1/simulations/sim_abc123/stop
curl -o results.parquet "http://localhost:8000/api/v1/data/export/sim_abc123?format=parquet"
```

**What you learned**: Creating simulations, starting/stopping, stepping
through, and exporting results.

---

## Tutorial 2: Custom Fluid Simulation

**Objective**: Set up and visualize a custom fluid simulation with
obstacles and force fields.

### Step 1: Define Fluid Parameters

```python
from simcore.fluid import StableFluidSimulator, BoundaryCondition

fluid = StableFluidSimulator(
    resolution=512,        # High resolution grid
    viscosity=0.1,         # Water-like viscosity
    diffusion=0.5,         # Density diffusion rate
    dt=0.016,              # ~60fps time step
)

# Set boundary conditions
fluid.set_boundary_conditions(BoundaryCondition(
    type="wrap",           # Periodic boundaries
    walls=["top", "bottom"],  # Solid walls on top/bottom
))
```

### Step 2: Add Obstacles

```python
# Central obstacle (sphere)
fluid.add_obstacle(
    x=256, y=256, radius=40,
    material="solid",
    restitution=0.5,
)

# Corner obstacles
fluid.add_obstacle(x=50, y=50, radius=15, material="solid")
fluid.add_obstacle(x=460, y=460, radius=15, material="solid")
```

### Step 3: Add Force Sources

```python
# Wind force from left
fluid.add_force(
    x=0, y=256,
    force=[1.0, 0.0],     # Push right
    radius=5,
    continuous=True,       # Apply every frame
)

# Downward gravity (already default, but can modify)
fluid.set_gravity([0.0, -0.5])
```

### Step 4: Add Density Injection

```python
# Inject dense fluid at center
fluid.add_force(
    x=256, y=256,
    force=[0.0, 0.0],
    radius=10,
    density_injection=1.0,  # Add density
    continuous=True,
)
```

### Step 5: Run and Visualize

```python
# Run simulation for 1000 steps
for i in range(1000):
    state = fluid.step()
    if i % 10 == 0:
        fluid.render(state, output_path=f"frame_{i:04d}.png")
        print(f"Step {i}: energy={state.total_energy:.4f}")
```

### Step 6: Export Animation

```bash
# Convert frames to video
ffmpeg -framerate 60 -i frame_%04d.png -c:v libx264 fluid_simulation.mp4
```

**What you learned**: Fluid grid setup, obstacles, force fields,
density injection, and frame-by-frame visualization.

---

## Tutorial 3: Train an MLP Model

**Objective**: Collect simulation data and train a neural network
to predict system behavior.

### Step 1: Collect Training Data

```python
from pipeline.collectors import SyntheticStreamCollector

collector = SyntheticStreamCollector(
    schema={
        "input_x": float,
        "input_y": float,
        "input_t": float,
        "output_force_x": float,
        "output_force_y": float,
    },
    noise_scale=0.01,
    drift=0.1,
    seed=42,
)

data = collector.collect(n=10000)
print(f"Collected {len(data)} records")
```

### Step 2: Prepare Data

```python
from pipeline.batch import clean_data, normalize_data

cleaned = clean_data(data, fill_strategy="mean")
normalized = normalize_data(cleaned, method="zscore")

# Split features and targets
import numpy as np
X = np.array([[r["input_x"], r["input_y"], r["input_t"]] for r in normalized])
y = np.array([[r["output_force_x"], r["output_force_y"]] for r in normalized])
```

### Step 3: Configure Training

```python
from pipeline.train import PipelineTrainer, TrainingConfig

config = TrainingConfig(
    epochs=200,
    batch_size=64,
    learning_rate=0.001,
    hidden_layers=(128, 64, 32),
    dropout_rate=0.1,
    early_stopping_patience=15,
    validation_split=0.2,
    seed=42,
)
```

### Step 4: Train the Model

```python
trainer = PipelineTrainer(config)
history = trainer.train(X, y)

print(f"Final loss: {history['final_loss']:.6f}")
print(f"Training time: {history['training_time_seconds']:.1f}s")
```

### Step 5: Save Checkpoint

```python
trainer.save_checkpoint("models/force_predictor.json")
print("Model saved to models/force_predictor.json")
```

### Step 6: Monitor Training

```python
import matplotlib.pyplot as plt

plt.plot(history["epoch"], history["loss"], label="Train")
plt.plot(history["epoch"], history["val_loss"], label="Validation")
plt.xlabel("Epoch")
plt.ylabel("Loss")
plt.legend()
plt.savefig("training_curve.png")
plt.show()
```

**What you learned**: Data collection, preprocessing, MLP training,
checkpoint management, and training visualization.

---

## Tutorial 4: SIR Epidemic Model

**Objective**: Set up and analyze an SIR epidemic simulation.

### Step 1: Define Parameters

```python
from simcore.integrator import VerletIntegrator
import numpy as np

# SIR parameters
beta = 0.3   # Transmission rate
gamma = 0.1  # Recovery rate
N = 10000    # Total population

# Initial conditions
S0 = N - 1     # Susceptible (all but one)
I0 = 1         # Infected
R0 = 0         # Recovered
```

### Step 2: Define ODE System

```python
def sir_ode(state, t, beta, gamma, N):
    S, I, R = state
    dSdt = -beta * S * I / N
    dIdt = beta * S * I / N - gamma * I
    dRdt = gamma * I
    return np.array([dSdt, dIdt, dRdt])
```

### Step 3: Simulate

```python
# Use RK4 for ODE integration (not Verlet, this is ODE not Hamiltonian)
from scipy.integrate import solve_ivp

t_span = (0, 200)
t_eval = np.linspace(0, 200, 1000)
state0 = [S0, I0, R0]

solution = solve_ivp(sir_ode, t_span, state0,
    args=(beta, gamma, N), t_eval=t_eval, method='RK45')

S, I, R = solution.y

# Analyze peak infection
peak_idx = np.argmax(I)
print(f"Peak infection at t={t_eval[peak_idx]:.1f}: {I[peak_idx]:.0f} infected")
print(f"Total recovered: {R[-1]:.0f}")
print(f"R0 (basic reproduction): {beta/gamma:.2f}")
```

### Step 4: Parameter Sensitivity

```python
for beta_val in [0.1, 0.2, 0.3, 0.5, 0.8]:
    solution = solve_ivp(sir_ode, t_span, state0,
        args=(beta_val, gamma, N), t_eval=t_eval)
    peak_I = np.max(solution.y[1])
    print(f"beta={beta_val:.1f}: peak_I={peak_I:.0f}")
```

**What you learned**: SIR model implementation, parameter analysis,
and epidemic dynamics visualization.

---

## Tutorial 5: Deploy with Docker

**Objective**: Containerize the platform for production deployment.

### Step 1: Create Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    redis-tools \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ ./backend/
COPY pipeline/ ./pipeline/
COPY simulation-core/ ./simulation-core/

# Create directories
RUN mkdir -p /app/checkpoints /app/data /app/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "backend.main"]
```

### Step 2: Create docker-compose.yml

```yaml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/sim
      - REDIS_URL=redis://cache:6379
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
    volumes:
      - ./checkpoints:/app/checkpoints
      - ./data:/app/data
    restart: unless-stopped

  db:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: sim
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 10s
      timeout: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
  redisdata:
```

### Step 3: Build and Run

```bash
# Build images
docker compose build

# Start services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f app

# Run pipeline inside container
docker compose exec app python -c "
from pipeline.collectors import SyntheticStreamCollector
collector = SyntheticStreamCollector({'x': float}, seed=42)
data = collector.collect(n=1000)
print(f'Collected {len(data)} records')
"

# Stop everything
docker compose down
```

### Step 4: Scale

```bash
# Scale backend instances
docker compose up -d --scale app=4

# Run with load balancer
# Add nginx or traefik in front
```

**What you learned**: Dockerfile creation, multi-container orchestration,
health checks, volumes, and scaling.
