#!/usr/bin/env bash
# Stop the v1 backend and website that run-local.sh started. Only the two processes in its pid files.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; RUN="${V1_RUN_DIR:-$ROOT/.run-v1}"
for name in backend web; do
  f="$RUN/$name.pid"
  [ -f "$f" ] || continue
  pid="$(cat "$f")"
  if ps -p "$pid" -o args= 2>/dev/null | grep -q -E 'uvicorn app.main:app|next start'; then
    kill "$pid" && echo "stopped v1 $name ($pid)"
  fi
  rm -f "$f"
done
