# complex-sim-platform — simulation-core

Módulo de simulação multi-modelo em Python puro + NumPy.

## Instalação rápida

```bash
pip install -r requirements.txt
```

## Uso rápido

```python
from simcore import SimulationEngine

# Partículas 2D
eng = SimulationEngine("particles", {"n": 200, "gravity": 9.81, "damping": 0.99})
eng.run(steps=100, dt=0.01)
print(eng.to_json())

# Rede neural
eng = SimulationEngine("neural", {"layers": [4, 8, 1], "activation": "relu", "seed": 42})
eng.run(steps=50, dt=0.0)

# Bio — SIR
eng = SimulationEngine("bio", {"model": "sir", "n_pop": 1000, "i0": 10})
eng.run(steps=200, dt=1.0)

# Fluidos
eng = SimulationEngine("fluids", {"size": 64, "viscosity": 0.0001})
eng.run(steps=10, dt=0.1)

# Corpos rígidos
eng = SimulationEngine("physics", {"n": 50, "gravity": 9.81})
eng.run(steps=100, dt=0.01)
```

## Exportação

```python
from simcore.state import save_json, load_json, to_csv
from simcore.export import export_csv, export_json, export_parquet, export_hdf5

save_json(eng.get_state(), "output.json")
export_csv(eng.get_state(), "output.csv")
```

## Tipos de simulação

| kind      | Descrição                                      |
|-----------|------------------------------------------------|
| particles | N partículas 2D com colisão (spatial hash)     |
| fluids    | Stable Fluids simplificado (grade 2D)          |
| physics   | Corpos rígidos 2D (círculos) com impulso       |
| neural    | MLP treinável do zero                           |
| bio       | SIR / Lotka-Volterra / Ecossistema grid         |
