#!/usr/bin/env bash
# Runs ON the GPU machine: start the v1 backend there (port 8110, loopback only), beside the model servers it calls.
# The website stays on the laptop and reaches this backend through one forwarded port (docs/v1/NEEDS_APPROVAL.md, item 2).
#
#   bash scripts/v1/vm-backend.sh          fit backend/.env to this machine, then start the backend
#   bash scripts/v1/vm-backend.sh --check  only say what it would do
#   bash scripts/v1/stop-local.sh          stop it again (only the process this started)
#
# It takes no GPU memory, needs no sudo and no Docker, and touches nothing of v0: no model server is started,
# stopped or configured, and CUDA MPS is left exactly as it is.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="${V1_DATA_DIR:-$HOME/bharatdb-v1/data}"
PORT="${V1_BACKEND_PORT:-8110}"
ENVF="$ROOT/backend/.env"
CHECK="${1:-}"
say() { echo "[vm-backend] $*"; }
answers() { [ "$(curl -s -o /dev/null -m 4 -w '%{http_code}' "$1" 2>/dev/null || true)" = "200" ]; }

[ -f "$ENVF" ] || { say "backend/.env is missing: copy the laptop's backend/.env here first (it holds the keys)"; exit 1; }
command -v python3 >/dev/null || { say "python3 is not on this machine"; exit 1; }
say "python3: $(python3 --version 2>&1)   (3.10 to 3.13 is what the backend was run on)"
if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then FF=1; say "ffmpeg: found"
else FF=0; say "WARNING: ffmpeg or ffprobe is not on the PATH. Live works without it; Studio does not."; fi
if answers "http://127.0.0.1:$PORT/health"; then
  say "REFUSED: something already answers on port $PORT. Stop it first (scripts/v1/stop-local.sh if it is this backend)."
  exit 1
fi
for p in 9001 9002 9003 9010 9030; do
  answers "http://127.0.0.1:$p/health" && say "model server :$p answers" || say "model server :$p does NOT answer (the backend will use its next provider)"
done
answers "http://127.0.0.1:9020/v1/models" && say "translation model :9020 answers" || say "translation model :9020 does NOT answer"
if command -v nvidia-smi >/dev/null; then
  say "GPU memory free: $(nvidia-smi --query-gpu=memory.free --format=csv,noheader 2>/dev/null | head -1) (the backend takes none)"
fi
say "data folder: $DATA"
if [ "$CHECK" = "--check" ]; then say "check only: nothing was changed or started"; exit 0; fi

# The laptop's .env names Windows paths; this machine gets its own. Keys are not read, printed or changed.
mkdir -p "$DATA"
chmod 600 "$ENVF"
sed -i -e 's/\r$//' "$ENVF"
set_var() { # set_var NAME VALUE: replace the line when it is there, add it when it is not
  if grep -q "^$1=" "$ENVF"; then sed -i -e "s#^$1=.*#$1=$2#" "$ENVF"; else printf '%s=%s\n' "$1" "$2" >> "$ENVF"; fi
}
set_var DATA_DIR "$DATA"
if [ "$FF" = "1" ]; then set_var FFMPEG_BIN ffmpeg; set_var FFPROBE_BIN ffprobe; fi
say "backend/.env: DATA_DIR and the ffmpeg paths set for this machine"

V1_SKIP_WEB=1 "$ROOT/scripts/v1/run-local.sh"
for _ in $(seq 1 90); do answers "http://127.0.0.1:$PORT/health" && break; sleep 2; done
if answers "http://127.0.0.1:$PORT/health"; then
  say "READY: the v1 backend answers on 127.0.0.1:$PORT. Log: $ROOT/.run-v1/backend.log"
else
  say "NOT READY after 3 minutes. Look at $ROOT/.run-v1/backend.log; stop it with scripts/v1/stop-local.sh"
  exit 1
fi
