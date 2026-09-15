#!/usr/bin/env bash
# restore.sh — restaura backups gerados por backup.sh
# Uso:
#   ./database/restore.sh backups/pg_complex_sim_20250101_120000.sql.gz
#   ./database/restore.sh --mongo backups/mongo_20250101_120000.tar.gz
#   ./database/restore.sh --list
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${POSTGRES_USER:-sim_user}"
PGDATABASE="${POSTGRES_DB:-complex_sim}"
export PGPASSWORD="${POSTGRES_PASSWORD:-changeme}"
MONGO_URI="${MONGO_URI:-mongodb://${MONGO_INITDB_ROOT_USERNAME:-admin}:${MONGO_INITDB_ROOT_PASSWORD:-changeme}@localhost:27017/?authSource=admin}"

usage() {
    echo "Uso: $0 <arquivo.sql.gz> | --mongo <arquivo.tar.gz> | --list"
    echo "  --list            lista backups em \$BACKUP_DIR"
    echo "  <arquivo.sql.gz>  restaura postgres via psql"
    echo "  --mongo <tar.gz>  restaura mongo via mongorestore"
    exit 1
}

if [[ $# -eq 0 ]]; then usage; fi

if [[ "$1" == "--list" ]]; then
    echo "Backups em $BACKUP_DIR:"
    ls -lh "$BACKUP_DIR" 2>/dev/null || echo "(vazio)"
    exit 0
fi

if [[ "$1" == "--mongo" ]]; then
    ARCHIVE="${2:-}"
    [[ -z "$ARCHIVE" ]] && usage
    if [[ ! -f "$ARCHIVE" ]]; then echo "ERRO: arquivo não encontrado: $ARCHIVE" >&2; exit 1; fi
    echo "[restore] mongo restore de $ARCHIVE"
    echo "[restore] URI: (oculta) — confirme antes de restaurar em produção!"
    read -r -p "Continuar? [y/N] " ans
    [[ "$ans" != "y" && "$ans" != "Y" ]] && { echo "Abortado."; exit 0; }
    TMPDIR="$(mktemp -d)"
    tar -xzf "$ARCHIVE" -C "$TMPDIR"
    DUMP_PATH="$(find "$TMPDIR" -type d -name "admin" -o -name "complex_sim" | head -n1 | xargs dirname 2>/dev/null || echo "$TMPDIR")"
    # tenta localizar diretório que contém .bson
    DUMP_PATH="$(find "$TMPDIR" -name "*.bson" -printf "%h\n" 2>/dev/null | head -n1 || echo "$TMPDIR")"
    if command -v mongorestore >/dev/null 2>&1; then
        mongorestore --uri="$MONGO_URI" --drop "$DUMP_PATH"
    elif docker compose -f "$ROOT/docker-compose.db.yml" ps --status running 2>/dev/null | grep -q mongo; then
        docker cp "$DUMP_PATH" complex-sim-mongo:/tmp/restore_dump
        docker compose -f "$ROOT/docker-compose.db.yml" exec -T mongo mongorestore --drop /tmp/restore_dump
        docker compose -f "$ROOT/docker-compose.db.yml" exec -T mongo rm -rf /tmp/restore_dump
    else
        echo "ERRO: mongorestore não encontrado" >&2; exit 1
    fi
    rm -rf "$TMPDIR"
    echo "[restore] mongo concluído."
    exit 0
fi

# postgres restore (default)
FILE="$1"
if [[ ! -f "$FILE" ]]; then echo "ERRO: arquivo não encontrado: $FILE" >&2; exit 1; fi

echo "[restore] postgres restore de $FILE -> $PGHOST:$PGPORT/$PGDATABASE"
echo "[restore] ATENÇÃO: isso irá sobrescrever dados!"
read -r -p "Digite o nome do DB para confirmar ($PGDATABASE): " confirm
if [[ "$confirm" != "$PGDATABASE" ]]; then echo "Abortado (nome não confere)."; exit 1; fi

if [[ "$FILE" == *.gz ]]; then
    DECOMP="gzip -dc"
else
    DECOMP="cat"
fi

if command -v psql >/dev/null 2>&1; then
    $DECOMP "$FILE" | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1
elif docker compose -f "$ROOT/docker-compose.db.yml" ps --status running 2>/dev/null | grep -q postgres; then
    $DECOMP "$FILE" | docker compose -f "$ROOT/docker-compose.db.yml" exec -T postgres psql -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1
else
    echo "ERRO: psql não encontrado e container não está rodando" >&2; exit 1
fi

echo "[restore] postgres concluído. Verifique com:"
echo "  psql -h $PGHOST -U $PGUSER -d $PGDATABASE -c 'SELECT count(*) FROM simulations;'"
