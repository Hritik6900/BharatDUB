#!/usr/bin/env bash
# A second v1 backend for an on/off comparison: its own port and data folder, every v1 flag off except the ones
# given. Never 8010 (v0); 8110 is the main v1 backend.
#   scripts/v1/ab-server.sh 8112 dynamic V1_PHRASE_DYNAMIC=true [MORE=..]
set -euo pipefail
PORT="${1:?port}"; NAME="${2:?name}"; shift 2
case "$PORT" in 3000|8010|8110|90[0-4][0-9]) echo "port $PORT is taken by v0, v1 or a model server"; exit 1;; esac
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
for f in V1_ROUTER V1_PHRASE_DYNAMIC V1_TTS_SERVER V1_TTS_MAYA V1_LIVE_STOCK_DEFAULT \
         V1_LIVE_LATE_SHORTEN V1_LIVE_BACKCHECK V1_STUDIO_HQ V1_FIT_115 \
         V1_BREAKER V1_LIVE_DEGRADE V1_API_LOG \
         V1_LIVE_BUDGET V1_LIVE_RATECTRL V1_LIVE_NATIVE_SPEED V1_LIVE_WARMSTART V1_EN_SINGLE_VOICE \
         V1_HQ_JUDGE V1_HQ_CALIBRATE V1_HQ_ADAPTIVE V1_HQ_NORMALISE V1_HQ_AUTO_GLOSSARY V1_HQ_REVIEW V1_LIVE_RECORD V1_LISTEN_TEST; do export "$f=false"; done
export V1_TRACE=true
for pair in "$@"; do export "$pair"; done
export DATA_DIR="${V1_DATA_DIR:-$ROOT/data-v1}/ab/$NAME" PUBLIC_API_BASE="http://localhost:$PORT"
mkdir -p "$DATA_DIR"
cd "$ROOT/backend"
PY=".venv/bin/python"; [ -x "$PY" ] || PY=".venv/Scripts/python.exe"   # the second on Windows (Git Bash)
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
