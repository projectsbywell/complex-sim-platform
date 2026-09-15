-- init.sql — schema consolidado Complex Sim Platform
-- Compatível PostgreSQL 16 + TimescaleDB. Para SQLite fallback veja db_client.py
-- Ordem: extensões -> tabelas -> índices -> hypertable -> permissões

-- extensões
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "timescaledb" SCHEMA public;

-- =========================
-- users
-- =========================
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          VARCHAR(32) NOT NULL DEFAULT 'researcher'
                  CHECK (role IN ('admin','researcher','viewer','service')),
    display_name  VARCHAR(120),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- =========================
-- simulations
-- =========================
CREATE TABLE IF NOT EXISTS simulations (
    id         SERIAL PRIMARY KEY,
    owner_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    type       VARCHAR(64) NOT NULL CHECK (type IN ('particles','fluids','physics','sir','lotka','ml','generic')),
    name       VARCHAR(200) NOT NULL DEFAULT 'Untitled',
    config     JSONB NOT NULL DEFAULT '{}'::jsonb,
    status     VARCHAR(32) NOT NULL DEFAULT 'created'
               CHECK (status IN ('created','queued','running','completed','failed','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_simulations_owner ON simulations(owner_id);
CREATE INDEX IF NOT EXISTS idx_simulations_type ON simulations(type);
CREATE INDEX IF NOT EXISTS idx_simulations_status ON simulations(status);
CREATE INDEX IF NOT EXISTS idx_simulations_config_gin ON simulations USING GIN (config);

-- =========================
-- runs
-- =========================
CREATE TABLE IF NOT EXISTS runs (
    id             SERIAL PRIMARY KEY,
    simulation_id  INTEGER NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    status         VARCHAR(32) NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','running','completed','failed')),
    params         JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_run_time CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);
CREATE INDEX IF NOT EXISTS idx_runs_simulation ON runs(simulation_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

-- =========================
-- metrics_timeseries (TimescaleDB hypertable)
-- =========================
CREATE TABLE IF NOT EXISTS metrics_timeseries (
    time        TIMESTAMPTZ NOT NULL,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    metric_name VARCHAR(128) NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    labels      JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- hypertable (idempotente)
SELECT create_hypertable('metrics_timeseries', 'time', if_not_exists => TRUE, migrate_data => TRUE);
-- compressão + retenção (opcional, comentada por compatibilidade)
-- SELECT add_compression_policy('metrics_timeseries', INTERVAL '7 days', if_not_exists => TRUE);
-- SELECT add_retention_policy('metrics_timeseries', INTERVAL '90 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_metrics_run_time ON metrics_timeseries(run_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON metrics_timeseries(metric_name, time DESC);

-- view agregada exemplo (bucket 1 minuto)
-- CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1m ...

-- =========================
-- audit_log
-- =========================
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    actor      VARCHAR(255) NOT NULL,
    action     VARCHAR(128) NOT NULL,
    resource   VARCHAR(255) NOT NULL,
    timestamp  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details    JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip         INET,
    request_id VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_details_gin ON audit_log USING GIN (details);

-- trigger updated_at
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_sim_updated ON simulations;
CREATE TRIGGER trg_sim_updated BEFORE UPDATE ON simulations FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- permissões mínimas (ajuste conforme env)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sim_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sim_user;
