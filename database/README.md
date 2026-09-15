# Database — Complex Sim Platform

Stack híbrido: **PostgreSQL 16 + TimescaleDB** (relacional + séries temporais), **MongoDB 7** (documentos flexíveis), **MinIO** (S3 compatível para artefatos).

## Arquitetura

```
┌─────────────┐   ┌──────────────┐   ┌─────────┐
│ PostgreSQL  │   │  MongoDB 7   │   │ MinIO   │
│ +TimescaleDB│   │  (docs)      │   │ (S3)    │
│ :5432       │   │  :27017      │   │ :9000/  │
│ metrics_*   │   │  sim blobs   │   │ 9001    │
└─────────────┘   └──────────────┘   └─────────┘
       ▲ selectable via db_client.py (psycopg2 ou fallback sqlite)
```

## Quick start

```bash
docker compose -f docker-compose.db.yml up -d
# verifica
docker compose -f docker-compose.db.yml ps
psql "postgresql://sim_user:sim_pass@localhost:5432/complex_sim" -f init.sql
# ou via wrapper Python
python database/db_client.py
```

Variáveis de ambiente (não hardcodadas — use `.env`):
```env
POSTGRES_USER=sim_user
POSTGRES_PASSWORD=<secret>
POSTGRES_DB=complex_sim
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=<secret>
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<secret>
```

## Tabelas principais (PostgreSQL)

| Tabela | Propósito |
|---|---|
| `users` | autenticação (id, email unique, password_hash, role, created_at) |
| `simulations` | metadados de simulação (id, owner_id FK, type, config JSONB, status, created_at) |
| `runs` | execuções (id, simulation_id FK, started_at, finished_at, status) |
| `metrics_timeseries` | hypertable TimescaleDB (time, run_id, metric_name, value) |
| `audit_log` | trilha de auditoria (id, actor, action, resource, timestamp, details JSONB) |

## TimescaleDB

`metrics_timeseries` é convertida em hypertable. Queries de agregação em `timescale_queries.sql`.

## MongoDB

Coleção `simulations_raw` para blobs JSON grandes / estados intermediários. Acesso via `mongodb://localhost:27017`.

## MinIO (S3)

Bucket `sim-artifacts` para relatórios, dumps e binários. Endpoint `http://localhost:9000`, console `:9001`.

## Backup & Restore

```bash
chmod +x database/backup.sh database/restore.sh
./database/backup.sh          # gera backups/ + rotação 7 dias
./database/restore.sh backups/pg_complex_sim_YYYYMMDD.sql.gz
```

## Migrações

```
migrations/001_init.sql       # baseline (users, simulations, runs)
migrations/002_timescale.sql  # hypertable + policies
migrations/003_audit.sql      # audit_log + índices
```

Aplicar na ordem ou usar `init.sql` (consolidado).

## Replicação

Ver `replication.md` — Postgres streaming primary→replica, Mongo replica set 3 nós, MinIO erasure/distributed.

## Cliente Python

`db_client.py` tenta `psycopg2`; se ausente ou sem servidor, cai para `sqlite` local (`./local.db`) mantendo mesma API:

```python
from database.db_client import Database
db = Database()  # auto-detecta
db.save_sim({"type": "sir", "config": {"beta": 0.3}})
db.log_metric(run_id=1, metric="infected", value=42.0)
row = db.load_sim(1)
```

## Segurança

- Nenhum segredo hardcoded; leia de env.
- `init.sql` cria role `sim_user` com privilégios mínimos (GRANT SELECT/INSERT/UPDATE, sem SUPERUSER).
- Conexão esperada via TLS (ver `security/crypto.py` checklist).
