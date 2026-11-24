#!/usr/bin/env bash
# Start v1 without containers: backend on 127.0.0.1:8110, website on 127.0.0.1:3100. v0 is not touched.
#   scripts/v1/run-local.sh            start both (builds the site when it has not been built)
#   V1_SKIP_WEB=1 scripts/v1/run-local.sh   the backend only
#   scripts/v1/stop-local.sh           stop what this script started (and only that)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_PORT="${V1_BACKEND_PORT:-8110}"; WEB_PORT="${V1_WEB_PORT:-3100}"
API="${V1_PUBLIC_ORIGIN:-http://localhost:$BACKEND_PORT}"; WS="${V1_PUBLIC_WS_ORIGIN:-ws://localhost:$BACKEND_PORT}"
RUN="${V1_RUN_DIR:-$ROOT/.run-v1}"; mkdir -p "$RUN"
for p in 3000 8010; do
  if [ "$BACKEND_PORT" = "$p" ] || [ "$WEB_PORT" = "$p" ]; then echo "port $p belongs to v0"; exit 1; fi
done
[ -f "$ROOT/backend/.env" ] || { echo "backend/.env is missing: copy backend/.env.example and fill it in"; exit 1; }

cd "$ROOT/backend"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu && .venv/bin/pip install -q -r requirements.txt; }
nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" > "$RUN/backend.log" 2>&1 &
echo $! > "$RUN/backend.pid"
# V1_SKIP_WEB=1: the backend alone (on the GPU machine, with the website still served from the laptop).
if [ "${V1_SKIP_WEB:-0}" = "1" ]; then
  echo "v1 backend: http://127.0.0.1:$BACKEND_PORT/api/v1/health   (website not started: V1_SKIP_WEB=1)   logs: $RUN"
  exit 0
fi

cd "$ROOT/web"
[ -d node_modules ] || npm ci --no-audit --no-fund
export NEXT_PUBLIC_API_BASE="$API" NEXT_PUBLIC_WS_BASE="$WS" NEXT_TELEMETRY_DISABLED=1
[ -d .next ] || npm run build
nohup npx next start -H 127.0.0.1 -p "$WEB_PORT" > "$RUN/web.log" 2>&1 &
echo $! > "$RUN/web.pid"
echo "v1 backend: http://127.0.0.1:$BACKEND_PORT/api/v1/health   website: http://127.0.0.1:$WEB_PORT/health   logs: $RUN"
