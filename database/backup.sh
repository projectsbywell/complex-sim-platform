#!/usr/bin/env bash
# backup.sh — pg_dump + mongodump + rotação 7 dias
# Uso: ./database/backup.sh
# Requer: pg_dump, mongodump (ou docker compose), gzip
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE="$(date +%Y%m%d_%H%M%S)"

# env com defaults (não hardcode secrets em repo — use .env)
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${POSTGRES_USER:-sim_user}"
PGDATABASE="${POSTGRES_DB:-complex_sim}"
export PGPASSWORD="${POSTGRES_PASSWORD:-changeme}"

MONGO_URI="${MONGO_URI:-mongodb://${MONGO_INITDB_ROOT_USERNAME:-admin}:${MONGO_INITDB_ROOT_PASSWORD:-changeme}@localhost:27017/?authSource=admin}"
MINIO_ALIAS="${MINIO_ALIAS:-local}"
MINIO_BUCKET="${MINIO_BUCKET:-sim-artifacts}"

mkdir -p "$BACKUP_DIR"

echo "[backup] $DATE — iniciando"

# --- PostgreSQL ---
PG_DUMP="$BACKUP_DIR/pg_${PGDATABASE}_${DATE}.sql.gz"
if command -v pg_dump >/dev/null 2>&1; then
    echo "[backup] pg_dump -> $PG_DUMP"
    pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" --no-owner --no-privileges | gzip -9 > "$PG_DUMP"
    echo "[backup] postgres OK: $(du -h "$PG_DUMP" | cut -f1)"
elif docker compose -f "$ROOT/docker-compose.db.yml" ps --status running 2>/dev/null | grep -q postgres; then
    echo "[backup] pg_dump via docker"
    docker compose -f "$ROOT/docker-compose.db.yml" exec -T postgres pg_dump -U "$PGUSER" -d "$PGDATABASE" | gzip -9 > "$PG_DUMP"
    echo "[backup] postgres OK (docker): $(du -h "$PG_DUMP" | cut -f1)"
else
    echo "[backup] WARN: pg_dump não encontrado e container não está rodando — pulando postgres"
fi

# --- MongoDB ---
MONGO_DUMP_DIR="$BACKUP_DIR/mongo_${DATE}"
MONGO_ARCHIVE="$BACKUP_DIR/mongo_${DATE}.tar.gz"
if command -v mongodump >/dev/null 2>&1; then
    echo "[backup] mongodump -> $MONGO_ARCHIVE"
    mongodump --uri="$MONGO_URI" --out="$MONGO_DUMP_DIR"
    tar -czf "$MONGO_ARCHIVE" -C "$BACKUP_DIR" "mongo_${DATE}"
    rm -rf "$MONGO_DUMP_DIR"
    echo "[backup] mongo OK: $(du -h "$MONGO_ARCHIVE" | cut -f1)"
elif docker compose -f "$ROOT/docker-compose.db.yml" ps --status running 2>/dev/null | grep -q mongo; then
    echo "[backup] mongodump via docker"
    docker compose -f "$ROOT/docker-compose.db.yml" exec -T mongo mongodump --out=/tmp/mongo_dump
    docker cp "complex-sim-mongo:/tmp/mongo_dump" "$MONGO_DUMP_DIR"
    tar -czf "$MONGO_ARCHIVE" -C "$BACKUP_DIR" "mongo_${DATE}"
    rm -rf "$MONGO_DUMP_DIR"
    docker compose -f "$ROOT/docker-compose.db.yml" exec -T mongo rm -rf /tmp/mongo_dump
    echo "[backup] mongo OK (docker): $(du -h "$MONGO_ARCHIVE" | cut -f1)"
else
    echo "[backup] WARN: mongodump não encontrado — pulando mongo"
fi

# --- MinIO (opcional, se mc configurado) ---
if command -v mc >/dev/null 2>&1 && mc alias list 2>/dev/null | grep -q "$MINIO_ALIAS"; then
    MIRROR_DIR="$BACKUP_DIR/minio_${DATE}"
    echo "[backup] mc mirror $MINIO_ALIAS/$MINIO_BUCKET -> $MIRROR_DIR"
    mkdir -p "$MIRROR_DIR"
    mc mirror --overwrite "$MINIO_ALIAS/$MINIO_BUCKET" "$MIRROR_DIR" || echo "[backup] WARN: mc mirror falhou"
fi

# --- Rotação ---
echo "[backup] rotação: removendo arquivos > ${RETENTION_DAYS}d em $BACKUP_DIR"
find "$BACKUP_DIR" -type f -mtime +"$RETENTION_DAYS" -print -delete || true
find "$BACKUP_DIR" -type d -mtime +"$RETENTION_DAYS" -print 2>/dev/null | head

# --- Checksum ---
if ls "$BACKUP_DIR"/*"$DATE"* >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && sha256sum *"$DATE"* > "SHA256_${DATE}.txt" || shasum -a 256 *"$DATE"* > "SHA256_${DATE}.txt")
    echo "[backup] checksums -> SHA256_${DATE}.txt"
fi

echo "[backup] concluído. Arquivos em $BACKUP_DIR:"
ls -lh "$BACKUP_DIR" | tail -n 20
