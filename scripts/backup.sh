#!/usr/bin/env bash
# PostgreSQL 백업 스크립트. DATABASE_URL(postgresql://...)에서 접속정보를 읽어 pg_dump 실행.
# SQLite 사용 시에는 이 스크립트 대신 `cp data/app.db backups/app-$(date +%F).db` 로 백업하세요.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/competitor-dashboard/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL 환경변수가 설정되어 있지 않습니다 (.env를 source 하거나 export 하세요)" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUT_FILE="$BACKUP_DIR/backup_${TIMESTAMP}.sql.gz"

pg_dump "$DATABASE_URL" | gzip > "$OUT_FILE"
echo "백업 완료: $OUT_FILE"

find "$BACKUP_DIR" -name 'backup_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete
