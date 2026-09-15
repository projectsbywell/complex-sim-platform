# Replicação — Complex Sim Platform

## 1. PostgreSQL 16 + TimescaleDB — Streaming Replication (primary → replica)

### Arquitetura

```
primary (read/write) ──WAL streaming──► replica (read-only, hot_standby=on)
   :5432                                 :5433
```

### Primary — `postgresql.conf`

```conf
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
wal_keep_size = 512MB        # ou wal_keep_segments para < PG13
listen_addresses = '*'
# opcional: archive_mode = on + archive_command para PITR
```

`pg_hba.conf` (primary):
```
host replication replicator replica_ip/32 scram-sha-256
host all         sim_user   0.0.0.0/0      scram-sha-256
```

Criar role de replicação:
```sql
CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '<secret>';
SELECT pg_create_physical_replication_slot('replica1_slot');
```

### Replica — base backup

```bash
# na réplica (postgres parado)
pg_basebackup -h primary_host -U replicator -D /var/lib/postgresql/data -X stream -R -S replica1_slot -P -v
# -R cria standby.signal + primary_conninfo automaticamente
```

`postgresql.conf` replica:
```conf
hot_standby = on
primary_conninfo = 'host=primary_host port=5432 user=replicator password=<secret> application_name=replica1'
```

Inicie a réplica:
```bash
docker compose -f docker-compose.db.yml up -d postgres-replica
# ou systemd: pg_ctl start
```

### Verificação

Primary:
```sql
SELECT * FROM pg_stat_replication;
SELECT * FROM pg_replication_slots;
```

Replica (read-only):
```sql
SELECT pg_is_in_recovery(); -- t
SELECT now() - pg_last_xact_replay_timestamp() AS lag;
```

Failover manual:
```bash
pg_ctl promote -D /var/lib/postgresql/data
# ou: touch /tmp/promote && SELECT pg_promote();
```

### docker-compose replica (adicionar ao docker-compose.db.yml)

```yaml
  postgres-replica:
    image: timescale/timescaledb:latest-pg16
    environment:
      PGUSER: replicator
      PGPASSWORD: ${REPLICATOR_PASSWORD}
    ports: ["5433:5432"]
    command: postgres -c hot_standby=on
    depends_on: [postgres]
```

> TimescaleDB é compatível com streaming físico; não use replicação lógica para hypertables sem `timescaledb` instalado na réplica.

---

## 2. MongoDB 7 — Replica Set (3 nós)

```yaml
# docker-compose override
  mongo1:
    image: mongo:7
    command: mongod --replSet rs0 --bind_ip_all
    ports: ["27017:27017"]
  mongo2:
    image: mongo:7
    command: mongod --replSet rs0 --bind_ip_all
    ports: ["27018:27017"]
  mongo3:
    image: mongo:7
    command: mongod --replSet rs0 --bind_ip_all
    ports: ["27019:27017"]
```

Inicialização (uma vez, no primary):
```javascript
mongosh --host mongo1:27017 <<'JS'
rs.initiate({
  _id: "rs0",
  members: [
    {_id: 0, host: "mongo1:27017"},
    {_id: 1, host: "mongo2:27017"},
    {_id: 2, host: "mongo3:27017"}
  ]
})
JS
mongosh --eval 'rs.status()'
```

URI da aplicação:
```
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/complex_sim?replicaSet=rs0&readPreference=secondaryPreferred
```

Keyfile para auth (prod):
```bash
openssl rand -base64 756 > keyfile && chmod 400 keyfile
# montar em cada nó e adicionar --keyFile /keyfile
```

---

## 3. MinIO — Distribuído / Erasure

Single-node já versiona (`sim-artifacts` com versioning). Para HA:

```bash
# 4 nós mínimo para erasure
minio server http://minio{1...4}/data{1...2} --console-address ":9001"
# ou via docker-compose com 4 serviços + nginx LB
mc admin replicate add minio1 minio2  # site replication
```

Backup MinIO já coberto em `backup.sh` via `mc mirror`.

---

## 4. Checklist operacional

- [ ] `.env` com senhas fortes em todos os nós; nunca comitar.
- [ ] TLS: `ssl = on` (PG) + `net.tls` (Mongo) + MinIO `MINIO_SERVER_URL` https via reverse proxy.
- [ ] Monitorar lag: `pg_stat_replication` + `rs.printSecondaryReplicationInfo()` + MinIO `mc admin trace`.
- [ ] Testar restore mensalmente (ver `restore.sh --list`).
- [ ] Retenção WAL + PITR: `archive_command = 'cp %p /wal/%f'` + `pgBackRest` ou `barman`.
