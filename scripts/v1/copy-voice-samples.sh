#!/usr/bin/env bash
# One-time copy of v0's voice sample files into v1's data folder. The source is only read; files already copied
# are left alone. Only the audio is copied: a voice profile also needs its consent record, which lives in v0's
# store and is not read, so a voice is recorded again in v1 (with consent) before v1 copies it.
#   scripts/v1/copy-voice-samples.sh <v0 voices folder> [v1 data folder]
set -euo pipefail
SRC="${1:?give the voices folder of v0, e.g. /path/to/v0/backend/data/voices}"
DST="${2:-${V1_DATA_DIR:-/srv/bharatdb-v1/data}}/v0_voice_samples"
[ -d "$SRC" ] || { echo "no such folder: $SRC"; exit 1; }
mkdir -p "$DST"
n=0
for f in "$SRC"/*; do
  [ -f "$f" ] || continue
  [ -e "$DST/$(basename "$f")" ] && continue
  cp -p "$f" "$DST/" && n=$((n + 1))
done
echo "copied $n new files to $DST ($(ls "$DST" | wc -l) there now)"
