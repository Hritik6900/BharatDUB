#!/usr/bin/env bash
# The whole v1 eval, one thing at a time (one GPU and one hosted account: never two runs at once).
#   scripts/v1/eval-all.sh <eval data folder> <out folder>
# Needs: a "flags off" v1 backend on V1_OFF (default 8111, scripts/v1/ab-server.sh 8111 base), the v1 backend with
# the HQ path on V1_HQ (default 8110). v0 is not run against unless V0 is set to its address: a test session on v0
# is a session in the product people use, so that is the owner's call.
# The eval data folder holds reel25.mp4 (Live), class12*.mp4 (Studio) and stt_set/ (speech-to-text).
set -uo pipefail
DATA="${1:?eval data folder}"; OUT="${2:?out folder}"
V0="${V0-}"; V1_OFF="${V1_OFF:-http://127.0.0.1:8111}"; V1_HQ="${V1_HQ:-http://127.0.0.1:8110}"
RUNS="${RUNS:-3}"; LANGS="${LANGS:-ta-IN,bn-IN}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
PY=".venv/bin/python"; [ -x "$PY" ] || PY=".venv/Scripts/python.exe"

echo "== Live: v0 against v1 with every flag off =="
targets=(--target "v1_off=$V1_OFF")
[ -n "$V0" ] && targets=(--target "v0=$V0" "${targets[@]}")
"$PY" -m eval.v1.live "$DATA/reel25.mp4" --out "$OUT/live_v0_v1" --runs "$RUNS" --loops 3 --langs "$LANGS" \
  --engine gpu --voice stream --v0 "" "${targets[@]}"

echo "== Studio: standard against HQ, one video at a time =="
for v in "$DATA"/class12*.mp4; do
  name="$(basename "$v" .mp4)"
  "$PY" -m eval.v1.studio "$v" --out "$OUT/studio_$name" --langs "$LANGS" --runs 1 --engine gpu --voice video \
    --target "standard=$V1_OFF" --target "hq=$V1_HQ:hq"
done

echo "== Speech-to-text: key words on the hard set =="
"$PY" -m eval.v1.stt --set "$DATA/stt_set" --out "$OUT/stt" --runs "$RUNS"
echo "done: $OUT"
