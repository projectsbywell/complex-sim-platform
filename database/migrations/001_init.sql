-- 001_init.sql — baseline relacional
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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
CREATE INDEX IF NOT EXISTS idx_simulations_config_gin ON simulations USING GIN (config);

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

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_sim_updated ON simulations;
CREATE TRIGGER trg_sim_updated BEFORE UPDATE ON simulations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
