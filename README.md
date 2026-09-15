# complex-sim-platform

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](https://opensource.org/licenses/MIT)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://github.com)
[![Coverage](https://img.shields.io/badge/coverage-85%25-blue)](https://github.com)
[![Docker](https://img.shields.io/badge/docker-supported-blue)](https://docker.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-orange)](https://fastapi.tiangolo.com)
[![NumPy](https://img.shields.io/badge/NumPy-1.24%2B-red)](https://numpy.org)

**Plataforma de Simulação Complexa** — Simulação, análise e treinamento
de sistemas complexos.

---

## Visão Geral

complex-sim-platform é uma plataforma completa para simulação,
análise e treinamento de sistemas complexos. Combina motores de
simulação de alta fidelidade, pipeline de dados robusto e
infraestrutura de ML em uma única plataforma integrada.

### Simuladores Disponíveis

| Módulo | Método | Aplicação |
|--------|--------|-----------|
| **Partículas** | Verlet Integrator | Dinâmica de partículas, conservação energética |
| **Fluidos** | Stable Fluids (Stam 1999) | Simulação de fluidos incompressíveis em tempo real |
| **Contato** | Box2D-lite Sequential Impulse | Detecção e resolução de colisões |
| **ML** | MLP + Adam Optimizer | Treinamento neural para augmentação de simulações |
| **Epidemia** | SIR Kermack-McKendrick | Modelagem de propagação de doenças |
| **Ecologia** | Lotka-Volterra | Dinâmica predador-presas |

---

## Quickstart

### 1. Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/complex-sim-platform.git
cd complex-sim-platform

# Crie ambiente virtual
python -m venv venv
source venv/bin/activate

# Instale dependências
pip install -r pipeline/requirements.txt
pip install -e .
```

### 2. Inicie o Servidor

```bash
python backend/main.py
# Servidor disponível em http://localhost:8000
```

### 3. Crie sua Primeira Simulação

```python
from pipeline.collectors import SyntheticStreamCollector
from pipeline.train import PipelineTrainer

# Colete dados
collector = SyntheticStreamCollector(
    schema={"x": float, "y": float}, seed=42
)
data = collector.collect(n=1000)

# Treine um modelo
trainer = PipelineTrainer()
history = trainer.train(X, y)
```

### 4. Acesso à API

```bash
# Criar simulação
curl -X POST http://localhost:8000/api/v1/simulations \
  -H "Content-Type: application/json" \
  -d '{"name": "meu-fluido", "type": "fluid"}'

# WebSocket em tempo real
# ws://localhost:8000/ws/v1/simulations/{id}
```

---

## Estrutura do Projeto

```
complex-sim-platform/
├── backend/                  # Servidor FastAPI (REST + WS)
│   ├── app/
│   │   ├── api/             # Endpoints REST
│   │   ├── ws/              # WebSocket handlers
│   │   ├── middleware/      # Auth, rate limit, CORS
│   │   └── schemas/         # Pydantic models
│   ├── main.py              # Entry point
│   └── config.py            # Application config
├── simulation-core/         # Motores de simulação
│   ├── integrator.py        # Verlet integrator
│   ├── fluid.py             # Stable Fluids (Stam 1999)
│   ├── contact.py           # Box2D-lite contact solver
│   ├── neural.py            # MLP with Adam
│   └── utils.py             # Shared utilities
├── pipeline/                # Pipeline de dados
│   ├── collectors.py        # API, CSV, synthetic sources
│   ├── batch.py             # Clean, normalize, aggregate
│   ├── stream.py            # Real-time stream consumer
│   ├── quality.py           # Schema validation, outliers
│   ├── train.py             # Neural network training
│   ├── infer.py             # Model inference engine
│   ├── requirements.txt     # Python dependencies
│   └── README.md            # Pipeline documentation
├── docs/                    # Documentação completa
│   ├── RESEARCH.md          # Algorithm research paper
│   ├── architecture.md      # System architecture + ADRs
│   ├── modules-*.md         # Per-module documentation
│   ├── tutorials.md         # Step-by-step guides
│   ├── examples.md          # Executable code snippets
│   ├── FAQ.md               # 20 most frequent questions
│   ├── CONTRIBUTING.md      # Contribution guide
│   ├── SECURITY.md          # Security architecture
│   └── GLOSSARY.md          # Technical glossary
├── i18n/                    # Internationalization
│   ├── pt-BR.json           # Português Brasileiro
│   ├── en.json              # English
│   ├── es.json              # Español
│   ├── fr.json              # Français
│   ├── de.json              # Deutsch
│   ├── ja.json              # 日本語
│   └── zh-CN.json           # 简体中文
├── database/                # Database configurations
├── frontend/                # React web application
├── infra/                   # Infrastructure as Code
├── security/                # Security policies and configs
├── tests/                   # Test suite
└── README.md                # This file
```

---

## Badges Disponíveis

- **Python**: 3.10+
- **Framework**: FastAPI
- **Compute**: NumPy / Numba / JAX (optional)
- **Database**: TimescaleDB, PostgreSQL, Redis
- **Storage**: Parquet, HDF5
- **Container**: Docker, Kubernetes
- **CI/CD**: GitHub Actions, GitLab CI
- **License**: MIT

---

## Roadmap

### v1.0 — Core Platform (Atual)
- [x] Verlet integrator with energy conservation
- [x] Stable Fluids (Stam 1999) implementation
- [x] Box2D-lite contact solver
- [x] MLP with Adam optimizer
- [x] Pipeline: collect, batch, stream, quality, train, infer
- [x] FastAPI backend with REST and WebSocket
- [x] i18n: 7 languages (180+ keys each)
- [x] Docker deployment support
- [x] Complete documentation suite

### v1.1 — Scaling & Performance
- [ ] GPU acceleration via JAX
- [ ] Distributed training with multi-GPU
- [ ] Adaptive time-stepping for integrators
- [ ] GPU-accelerated fluid solver (CUDA)

### v1.2 — Advanced Features
- [ ] Real-time collaboration (multi-user editing)
- [ ] Automated hyperparameter tuning
- [ ] Model registry and versioning
- [ ] A/B testing framework for simulations

### v2.0 — Enterprise Features
- [ ] Multi-tenant architecture
- [ ] Advanced RBAC and SSO integration
- [ ] Audit trail and compliance reporting
- [ ] On-premise deployment kit

---

## Tecnologias

- **Linguagem**: Python 3.10+
- **Backend**: FastAPI (async REST + WebSocket)
- **Computação**: NumPy, Numba (optional), JAX (optional)
- **Banco de Dados**: TimescaleDB, PostgreSQL, Redis
- **Armazenamento**: Parquet, HDF5
- **Containerização**: Docker, Kubernetes
- **CI/CD**: GitHub Actions, GitLab CI
- **Frontend**: React + TypeScript (opcional)
- **Monitoramento**: Prometheus, Grafana, OpenTelemetry
- **Tradução**: 7 idiomas com JSON localization

---

## Licença

MIT License — See [LICENSE](LICENSE) for details.

---

## Contato

- **Issues**: [GitHub Issues](https://github.com/complex-sim-platform/issues)
- **Discussions**: [GitHub Discussions](https://github.com/complex-sim-platform/discussions)
- **Documentation**: [docs/](docs/)
- **Email**: hello@complex-sim-platform.dev
