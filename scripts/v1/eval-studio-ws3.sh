#!/usr/bin/env bash
# v1.1 WS3: the Studio comparison, one job at a time, never while a stream is live.
#   scripts/v1/eval-studio-ws3.sh <eval data folder> <out folder> [video ...]
# Expects one comparison backend per setup, each with its own data folder. Start them from PowerShell
# (scripts\v1\ab-server.ps1), where stopping the task also stops the backend; a backend started through Git Bash
# on Windows keeps running when its task is stopped.
#   8111 ws3-std     V1_HQ_JUDGE=true                                   (standard jobs; the flag only sets the judge of the eval route)
#   8112 ws3-hq      V1_STUDIO_HQ V1_FIT_115 V1_ROUTER V1_HQ_JUDGE      (HQ as v1 built it, with the judge)
#   8113 ws3-fixed   the same + V1_HQ_TAKES_FIXED=5
#   8114 ws3-adapt   the same + V1_HQ_ADAPTIVE=true
#   8115 ws3-new     the same + V1_HQ_ADAPTIVE V1_HQ_NORMALISE V1_HQ_AUTO_GLOSSARY V1_HQ_REVIEW
# SETUPS says which of them to run and where: "name:port[:hq] ...". SEED_TO names the data folders that get the HQ
# backend's transcript and translation from its cache before their job (SEED_FROM), so that those setups speak the
# same lines as the HQ job and differ only in how many takes they make.
set -uo pipefail
DATA="${1:?eval data folder}"; OUT="${2:?out folder}"; shift 2
mkdir -p "$OUT"; DATA="$(cd "$DATA" && pwd)"; OUT="$(cd "$OUT" && pwd)"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AB="${V1_DATA_DIR:-$ROOT/data-v1}/ab"
LANGS="${LANGS:-ta-IN,bn-IN}"
SETUPS="${SETUPS:-std:8111 hq:8112:hq fixed:8113:hq adapt:8114:hq new:8115:hq}"
SEED_FROM="${SEED_FROM:-ws3-hq}"; SEED_TO="${SEED_TO:-ws3-fixed ws3-adapt}"
VIDEOS=("$@"); [ ${#VIDEOS[@]} -gt 0 ] || VIDEOS=(class12 class12b class12c)
cd "$ROOT/backend"
PY=".venv/bin/python"; [ -x "$PY" ] || PY=".venv/Scripts/python.exe"

quiet() {   # 0 when no stream is live on v0 or v1; waits up to 30 minutes for one to end
  for _ in $(seq 1 30); do
    if ! { curl -s -m 8 http://127.0.0.1:8010/api/live/sessions; curl -s -m 8 http://127.0.0.1:8110/api/live/sessions; } \
         | LC_ALL=C grep -q '"status": *"live"'; then return 0; fi
    echo "a stream is live: waiting 60 s"; sleep 60
  done
  return 1
}

job() {     # job <video> <name> <port> [hq]
  local video="$1" name="$2" port="$3" hq="${4:-}"
  if [ -f "$OUT/${video}_$name/summary.json" ]; then echo "== $video $name: already there"; return; fi
  if ! quiet; then echo "SKIPPED $video $name: a stream was still live after 30 minutes"; return; fi
  echo "== $video $name $(date +%H:%M:%S)"
  "$PY" -m eval.v1.studio "$DATA/$video.mp4" --out "$OUT/${video}_$name" --langs "$LANGS" --runs 1 --engine gpu \
      --voice video --target "$name=http://127.0.0.1:$port${hq:+:hq}" > "$OUT/${video}_$name.log" 2>&1
  head -1 "$OUT/${video}_$name.log"
}

seed() {    # the HQ backend's audio and text work, not its takes or scores. Not `clone` either: a cached copy of
            # the voice names a sample file in the other backend's voices folder, our engine then cannot speak
            # and the whole job is said by the hosted copy (seen on the first try of this script).
  for to in $SEED_TO; do
    mkdir -p "$AB/$to/cache"
    for stage in separate segment transcribe transcribe_hq translate_hq diarize_hq; do
      [ -d "$AB/$SEED_FROM/cache/$stage" ] && cp -r "$AB/$SEED_FROM/cache/$stage" "$AB/$to/cache/"
    done
  done
}

for v in "${VIDEOS[@]}"; do
  seed
  for setup in $SETUPS; do
    IFS=: read -r name port hq <<< "$setup"
    job "$v" "$name" "$port" "$hq"
    [ "$name" = hq ] && seed
  done
done
echo "done: $OUT $(date +%H:%M:%S)"
