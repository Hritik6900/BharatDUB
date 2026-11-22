#!/usr/bin/env bash
# Copy v1's data and configuration to a Cloud Storage bucket. Keys are NOT copied: backend/.env stays on the VM.
#   V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh [--dry]
# What goes: the store (JSON file, or a Postgres dump), voice samples, the trace, routing and compose files.
# What does not go: the cache, uploads and rendered jobs (they can be made again), and anything with a key in it.
# Needs `gcloud storage` (or `gsutil`) signed in on the VM with write access to the bucket.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="${V1_DATA_DIR:-/srv/bharatdb-v1/data}"
BUCKET="${V1_BACKUP_BUCKET:-}"
DRY="${1:-}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [ -z "$BUCKET" ]; then
  echo "V1_BACKUP_BUCKET is not set (gs://<bucket>/<folder>). Nothing was copied."; exit 2
fi
if command -v gcloud >/dev/null 2>&1; then CP=(gcloud storage cp -r); elif command -v gsutil >/dev/null 2>&1; then CP=(gsutil -m cp -r);
else echo "neither gcloud nor gsutil is installed. Nothing was copied."; exit 2; fi

WORK="$(mktemp -d)"; trap 'rm -r "$WORK"' EXIT
mkdir -p "$WORK/config"
for f in backend/config/routing.yaml docker-compose.v1.yml gpu_engine_v1/docker-compose.models.yml Caddyfile.v1; do
  [ -f "$ROOT/$f" ] && cp "$ROOT/$f" "$WORK/config/"
done
# The names of the settings in use, never their values.
[ -f "$ROOT/backend/.env" ] && sed -E 's/=.*/=/' "$ROOT/backend/.env" > "$WORK/config/env-names.txt"
git -C "$ROOT" rev-parse HEAD > "$WORK/config/commit.txt" 2>/dev/null || true

items=("$WORK/config")
[ -f "$DATA/local_db.json" ] && items+=("$DATA/local_db.json")
[ -d "$DATA/voices" ] && items+=("$DATA/voices")
[ -d "$DATA/trace" ] && items+=("$DATA/trace")
if [ -n "${POSTGRES_DSN:-}" ] && command -v pg_dump >/dev/null 2>&1; then
  pg_dump "$POSTGRES_DSN" | gzip > "$WORK/postgres.sql.gz" && items+=("$WORK/postgres.sql.gz")
fi

for item in "${items[@]}"; do
  if [ "$DRY" = "--dry" ]; then echo "would copy: $item -> $BUCKET/$STAMP/"; else "${CP[@]}" "$item" "$BUCKET/$STAMP/"; fi
done
[ "$DRY" = "--dry" ] || echo "$(date -u +%FT%TZ) backup $STAMP -> $BUCKET" >> "$DATA/backup.log"
echo "backup $STAMP: ${#items[@]} items $([ "$DRY" = "--dry" ] && echo '(dry run)')"
