-- timescale_queries.sql — exemplos TimescaleDB para metrics_timeseries
-- Tabela: metrics_timeseries(time TIMESTAMPTZ, run_id INT, metric_name TEXT, value DOUBLE, labels JSONB)

-- 1. Bucket 1 minuto: média por métrica e run (últimas 24h)
SELECT
    time_bucket('1 minute', time) AS bucket,
    run_id,
    metric_name,
    avg(value)  AS avg_val,
    min(value)  AS min_val,
    max(value)  AS max_val,
    count(*)    AS n
FROM metrics_timeseries
WHERE time > now() - INTERVAL '24 hours'
GROUP BY bucket, run_id, metric_name
ORDER BY bucket DESC, run_id, metric_name
LIMIT 100;

-- 2. Downsample 1 hora com percentis (requer toolkit opcional)
SELECT
    time_bucket('1 hour', time) AS bucket,
    metric_name,
    avg(value) AS avg_val,
    percentile_agg(value) AS pct_agg  -- se tdigest/toolkit instalado
    -- approx_percentile(0.95, percentile_agg(value)) AS p95
FROM metrics_timeseries
WHERE time > now() - INTERVAL '7 days'
GROUP BY bucket, metric_name
ORDER BY bucket DESC;

-- 3. Último valor por run/métrica (distinct on / last)
SELECT DISTINCT ON (run_id, metric_name)
    run_id, metric_name, time, value
FROM metrics_timeseries
ORDER BY run_id, metric_name, time DESC;

-- Alternativa Timescale: last()
-- SELECT run_id, metric_name, last(value, time) FROM metrics_timeseries GROUP BY run_id, metric_name;

-- 4. Janela móvel (rolling avg 5 min) por run
SELECT
    time,
    run_id,
    metric_name,
    value,
    avg(value) OVER (
        PARTITION BY run_id, metric_name
        ORDER BY time
        RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND CURRENT ROW
    ) AS rolling_avg_5m
FROM metrics_timeseries
WHERE run_id = 1 AND metric_name = 'infected'
ORDER BY time DESC
LIMIT 200;

-- 5. Taxa de variação (delta por minuto)
SELECT
    time,
    value - lag(value) OVER (PARTITION BY run_id, metric_name ORDER BY time) AS delta,
    EXTRACT(EPOCH FROM (time - lag(time) OVER (PARTITION BY run_id, metric_name ORDER BY time))) AS dt_sec
FROM metrics_timeseries
WHERE run_id = 1
ORDER BY time;

-- 6. Comparação entre runs (pivot simplificado)
SELECT
    time_bucket('5 minutes', time) AS bucket,
    avg(value) FILTER (WHERE run_id = 1) AS run_1_avg,
    avg(value) FILTER (WHERE run_id = 2) AS run_2_avg,
    avg(value) FILTER (WHERE run_id = 3) AS run_3_avg
FROM metrics_timeseries
WHERE metric_name = 'energy'
GROUP BY bucket
ORDER BY bucket;

-- 7. Detecção de anomalia simples: z-score por bucket
WITH stats AS (
    SELECT metric_name, avg(value) AS mu, stddev(value) AS sd
    FROM metrics_timeseries
    WHERE time > now() - INTERVAL '1 hour'
    GROUP BY metric_name
)
SELECT m.time, m.metric_name, m.value,
       (m.value - s.mu) / NULLIF(s.sd,0) AS z
FROM metrics_timeseries m
JOIN stats s USING (metric_name)
WHERE abs((m.value - s.mu)/NULLIF(s.sd,0)) > 3
ORDER BY time DESC
LIMIT 100;

-- 8. Continuous aggregate (materializada) — descomente para criar
-- CREATE MATERIALIZED VIEW metrics_1m
-- WITH (timescaledb.continuous) AS
-- SELECT time_bucket('1 minute', time) AS bucket,
--        run_id, metric_name,
--        avg(value) AS avg_val, max(value) AS max_val
-- FROM metrics_timeseries
-- GROUP BY bucket, run_id, metric_name
-- WITH NO DATA;
-- SELECT add_continuous_aggregate_policy('metrics_1m',
--     start_offset => INTERVAL '1 hour',
--     end_offset   => INTERVAL '1 minute',
--     schedule_interval => INTERVAL '1 minute');

-- 9. Retenção/compressão policies
-- SELECT add_retention_policy('metrics_timeseries', INTERVAL '90 days');
-- SELECT add_compression_policy('metrics_timeseries', INTERVAL '7 days');

-- 10. Tamanho e chunks
SELECT hypertable_size('metrics_timeseries') AS total_bytes,
       pg_size_pretty(hypertable_size('metrics_timeseries')) AS pretty;
SELECT * FROM timescaledb_information.chunks WHERE hypertable_name='metrics_timeseries' LIMIT 20;
