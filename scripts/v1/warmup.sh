#!/usr/bin/env bash
# One small request through every service v1 uses, so the first real line is not the slow one.
# Uses the backend's own warm-up endpoint (it calls the providers the way a session would) and prints each time.
#   scripts/v1/warmup.sh [v1 backend] [language]
set -uo pipefail
API="${1:-${V1_API:-http://127.0.0.1:8110}}"; LANG_CODE="${2:-ta-IN}"
out="$(curl -s -m 90 -X POST "$API/api/v1/warmup?lang=$LANG_CODE" 2>/dev/null || true)"
if [ -z "$out" ]; then echo "FAIL  no answer from $API/api/v1/warmup"; exit 1; fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# A Python to read the answers with: the backend's own environment when it is there (on Windows `python3` can be
# a stub that only opens the Store), else whatever the machine has.
if [ -x "$ROOT/backend/.venv/bin/python" ]; then PY="$ROOT/backend/.venv/bin/python"
elif [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then PY="$ROOT/backend/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
printf '%s' "$out" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
bad = 0
for s in d["steps"]:
    mark = "ok   " if s["ok"] else ("skip " if s.get("skipped") else "FAIL ")
    bad |= (not s["ok"] and not s.get("skipped"))
    print("%s %-28s %6s ms  %s" % (mark, s["step"], s.get("ms", ""), s.get("note", "")))
print("warm" if not bad else "NOT warm")
sys.exit(bad)
'
