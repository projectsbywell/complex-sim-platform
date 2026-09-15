# Examples Data — Complex Sim Platform

Dados sintéticos para testes, demos e validação sem depender de Docker/DB.

## Arquivos

| Arquivo | Tipo | Descrição |
|---|---|---|
| `particles_demo.json` | JSON | 100 partículas (id, x,y,z, vx,vy,vz, mass) |
| `fluids_demo.json` | JSON | grid 16×16 de velocidade/pressão (Navier-Stokes simplificado) |
| `physics_demo.json` | JSON | 50 corpos rígidos (pos, vel, mass, radius) |
| `sir_demo.csv` | CSV | SIR 120 dias (S,I,R, beta, gamma) |
| `lotka_demo.csv` | CSV | Lotka-Volterra 200 passos (presa/predador) |
| `ml_train.csv` | CSV | 200 linhas sintéticas (regressão: 5 features + target) |

## Uso

```python
import json, csv
json.load(open("examples-data/particles_demo.json"))
list(csv.DictReader(open("sir_demo.csv")))
# ml
import csv, statistics
rows = list(csv.DictReader(open("ml_train.csv")))
```

Todos os arquivos são determinísticos (seed 42) e compatíveis com `pipeline/report_generator.py` e `simulation-core`.

## Licença

Dados sintéticos — uso livre para demo/teste.
