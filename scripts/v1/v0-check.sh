#!/usr/bin/env bash
# Is v0 still fine? Read-only: asks v0's own health endpoints and the shared GPU servers. Exit 0 = all answer.
#   scripts/v1/v0-check.sh [v0 backend] [v0 website]
V0_API="${1:-${V0_API:-http://127.0.0.1:8010}}"; V0_WEB="${2:-${V0_WEB:-http://127.0.0.1:3000}}"
GPU_HOST="${GPU_HOST:-http://127.0.0.1}"
bad=0
ask() { # name url
  code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$2" || true)
  if [ "$code" = "200" ]; then echo "ok   $1"; else echo "DOWN $1 ($code)"; bad=1; fi
}
ask "v0 backend" "$V0_API/health"
ask "v0 streamer health" "$V0_API/api/streamers/health"
ask "v0 website" "$V0_WEB/"
for p in 9001 9002 9003 9010 9030; do ask "gpu server $p" "$GPU_HOST:$p/health"; done
ask "gpu server 9020" "$GPU_HOST:9020/v1/models"
exit $bad
