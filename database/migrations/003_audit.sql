-- 003_audit.sql — trilha de auditoria
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
