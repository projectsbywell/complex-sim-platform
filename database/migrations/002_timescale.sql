-- 002_timescale.sql — séries temporais
CREATE EXTENSION IF NOT EXISTS "timescaledb" SCHEMA public;

CREATE TABLE IF NOT EXISTS metrics_timeseries (
    time        TIMESTAMPTZ NOT NULL,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    metric_name VARCHAR(128) NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    labels      JSONB NOT NULL DEFAULT '{}'::jsonb
);

SELECT create_hypertable('metrics_timeseries', 'time', if_not_exists => TRUE, migrate_data => TRUE);

CREATE INDEX IF NOT EXISTS idx_metrics_run_time ON metrics_timeseries(run_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON metrics_timeseries(metric_name, time DESC);

-- políticas opcionais (descomente em prod)
-- SELECT add_compression_policy('metrics_timeseries', INTERVAL '7 days', if_not_exists => TRUE);
-- SELECT add_retention_policy('metrics_timeseries', INTERVAL '90 days', if_not_exists => TRUE);
