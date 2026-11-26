#!/usr/bin/env bash
# Before a demo: is v1 ready? Read-only. Exit 0 = everything needed answers.
#   scripts/v1/demo-check.sh [v1 backend] [v1 website]
# Checks: v1 backend and website, every model server the backend is configured to call, the hosted services,
# free GPU memory, which GPU mode the card is in, that nobody else is live, the mode (auto or manual) and what is in force.
set -uo pipefail
API="${1:-${V1_API:-http://127.0.0.1:8110}}"; WEB="${2:-${V1_WEB:-http://127.0.0.1:3100}}"
V0_API="${V0_API:-http://127.0.0.1:8010}"
MIN_FREE_GB="${MIN_FREE_GB:-4}"
bad=0
ok()   { echo "ok    $*"; }
fail() { echo "FAIL  $*"; bad=1; }
warn() { echo "warn  $*"; }
code() { curl -s -o /dev/null -m 8 -w '%{http_code}' "$1" 2>/dev/null || true; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# A Python to read the answers with: the backend's own environment when it is there (on Windows `python3` can be
# a stub that only opens the Store), else whatever the machine has.
if [ -x "$ROOT/backend/.venv/bin/python" ]; then PY="$ROOT/backend/.venv/bin/python"
elif [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then PY="$ROOT/backend/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
py()   { "$PY" "$@"; }

[ "$(code "$API/health")" = "200" ] && ok "v1 backend $API" || fail "v1 backend $API does not answer"
[ "$(code "$WEB/")" = "200" ] && ok "v1 website $WEB" || fail "v1 website $WEB does not answer"

health="$(curl -s -m 20 "$API/api/v1/health" 2>/dev/null || true)"
if [ -z "$health" ]; then
  fail "no answer from $API/api/v1/health"
else
  printf '%s' "$health" | py -c '
import json, sys
h = json.load(sys.stdin)
bad = 0
for c in h["checks"]:
    if c["ok"]:
        print("ok    %-34s %5s ms" % (c["name"], c.get("ms", "")))
    elif c["kind"] == "hosted" and not c.get("configured"):
        print("warn  %-34s not configured" % c["name"])
    else:
        print("FAIL  %-34s %s" % (c["name"], c.get("error", "down")))
        bad = 1
f = h["flags"]
on = [k for k, v in f.items() if v is True]
print("mode: " + str(f.get("V1_MODE", "manual")) + "; overrides: " + (", ".join(f"{k}={v}" for k, v in (f.get("overrides") or {}).items()) or "none")
      + "; in force: " + (", ".join(on) if on else "nothing (behaves as v0)") + "; store: " + str(f.get("V1_STORE")))
g = h.get("gpu")
print("GPU %s: " % h.get("gpu_name", "A100 (VM)") + ("%.1f GB free of %.1f" % (g["free_gb"], g["total_gb"]) if g else "unknown (no /gpu endpoint on the VM yet)"))
for c in h.get("circuits") or []:
    if c["state"] != "closed":
        print("warn  circuit %s is %s for %s s (%s)" % (c["name"], c["state"], c.get("down_s"), c.get("reason", "")))
sys.exit(bad)
' || bad=1
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  free="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | awk '{printf "%d", $1/1024}')"
  card="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
  # This is the card of the machine the check runs on. On the VM that is the model servers' card; on a laptop it is not.
  if [ "${free:-0}" -ge "$MIN_FREE_GB" ]; then ok "card of the machine this check runs on ($card; the A100 only when run on the VM): $free GB free"; else warn "card of the machine this check runs on ($card; the A100 only when run on the VM): ${free:-?} GB free (under $MIN_FREE_GB GB)"; fi
fi
if [ "$(code http://127.0.0.1:9044/v1/models)" = "200" ]; then
  warn "GPU mode: HQ window (the big translation model is loaded; Live translates through the hosted model). Run: scripts/v1/gpu-mode.sh normal --run"
else
  ok "GPU mode: normal"
fi

for pair in "v0=$V0_API" "v1=$API"; do
  name="${pair%%=*}"; url="${pair#*=}"
  n="$(curl -s -m 6 "$url/api/live/sessions" 2>/dev/null | grep -o '"status":"live"' | wc -l | tr -d ' ')"
  if [ "${n:-0}" = "0" ]; then ok "no live session on $name"; else warn "$n live session(s) on $name: one GPU is one stream"; fi
done

echo
if [ "$bad" = "0" ]; then echo "READY"; else echo "NOT READY"; fi
exit "$bad"
