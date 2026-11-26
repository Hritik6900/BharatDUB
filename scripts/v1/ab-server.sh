#!/usr/bin/env bash
# A second v1 backend for a comparison: its own port and data folder. Never 8010 (v0); 8110 is the main v1 backend.
#
#   manual mode (the default): every v1 feature off except the ones given (as before v1.2), the trace on:
#       scripts/v1/ab-server.sh 8121 budget V1_LIVE_BUDGET=true [MORE=..]
#   auto mode (what v1 runs with): `--auto` after the name. KEY=VALUE pairs are settings (switches are ignored in
#   auto mode); OVERRIDES switches single behaviours off for this backend:
#       scripts/v1/ab-server.sh 8120 auto --auto
#       OVERRIDES="live_stock_default=off" scripts/v1/ab-server.sh 8122 auto-learned --auto
#
# An auto backend never reads backend/config/overrides.yaml: it gets a file of its own in its data folder, holding
# exactly what OVERRIDES says (nothing, when it is not set), so a comparison does not depend on that file.
set -euo pipefail
PORT="${1:?port}"; NAME="${2:?name}"; shift 2
MODE=manual
if [ "${1:-}" = "--auto" ]; then MODE=auto; shift; fi
case "$PORT" in 3000|3100|8010|8110|90[0-4][0-9]) echo "port $PORT is taken by v0, v1 or a model server"; exit 1;; esac
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export DATA_DIR="${V1_DATA_DIR:-$ROOT/data-v1}/ab/$NAME" PUBLIC_API_BASE="http://localhost:$PORT" V1_MODE="$MODE"
mkdir -p "$DATA_DIR"
if [ "$MODE" = manual ]; then
  [ -z "${OVERRIDES:-}" ] || { echo "OVERRIDES is for --auto (manual mode does not read overrides)"; exit 1; }
  for f in V1_ROUTER V1_TTS_SERVER V1_TTS_MAYA V1_LIVE_STOCK_DEFAULT \
           V1_LIVE_LATE_SHORTEN V1_LIVE_BACKCHECK V1_STUDIO_HQ V1_FIT_115 \
           V1_BREAKER V1_LIVE_DEGRADE V1_API_LOG V1_LIVE_BUDGET V1_EN_SINGLE_VOICE \
           V1_HQ_JUDGE V1_HQ_CALIBRATE V1_HQ_ADAPTIVE V1_HQ_NORMALISE V1_HQ_AUTO_GLOSSARY V1_HQ_REVIEW V1_LIVE_RECORD V1_LISTEN_TEST; do export "$f=false"; done
  export V1_TRACE=true V1_OVERRIDES_FILE=
else
  export V1_OVERRIDES_FILE="$DATA_DIR/overrides.yaml"
  { echo "# written by scripts/v1/ab-server.sh for the comparison backend '$NAME'"
    IFS=','; for pair in ${OVERRIDES:-}; do [ -z "$pair" ] || echo "${pair%%=*}: ${pair#*=}"; done; unset IFS
  } > "$V1_OVERRIDES_FILE"
fi
for pair in "$@"; do export "$pair"; done
cd "$ROOT/backend"
PY=".venv/bin/python"; [ -x "$PY" ] || PY=".venv/Scripts/python.exe"   # the second on Windows (Git Bash)
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
