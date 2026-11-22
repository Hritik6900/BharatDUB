#!/usr/bin/env bash
# Switch the one GPU between its two jobs. Run on the VM, by the person who owns it.
#
#   gpu-mode.sh status          what answers now and how much GPU memory is free (read-only)
#   gpu-mode.sh hq [--run]      HQ window: stop the small translation model (:9020), start the big one (:9044)
#                               and Indic Transcribe (:9043). While it lasts, v0 and v1 Live translate through the
#                               hosted model by themselves (their fallback), so do this when nobody is live.
#   gpu-mode.sh normal [--run]  back: stop :9044 and :9043, start the small model again with v0's own start script
#
# Without --run every command is only printed (a dry run). Every real switch is written to the log with its time.
# It never touches the voice engines (9001-9003), Demucs (9010) or the live speech-to-text (9030).
set -euo pipefail

MODE="${1:-status}"; RUN="${2:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
V0_ENGINE_DIR="${V0_ENGINE_DIR:-$HOME/voice_engine}"          # where v0's start_llm.sh lives
V0_API="${V0_API:-http://127.0.0.1:8010}"; V1_API="${V1_API:-http://127.0.0.1:8110}"
SMALL_MODEL="${LLM_MODEL:-google/gemma-4-E4B-it}"
COMPOSE=(docker compose -p bharatdb-v1-models -f "$ROOT/gpu_engine_v1/docker-compose.models.yml")
LOG="${V1_DATA_DIR:-/srv/bharatdb-v1/data}/gpu-mode.log"
NEED_FREE_GB="${HQ_NEED_FREE_GB:-20}"                          # the big model + Indic Transcribe + 4 GB of headroom

say() { echo "[gpu-mode $(date -u +%H:%M:%S)] $*"; }
log() { mkdir -p "$(dirname "$LOG")" 2>/dev/null || true; echo "$(date -u +%FT%TZ) $*" >> "$LOG" 2>/dev/null || true; }
do_() { if [ "$RUN" = "--run" ]; then say "run: $*"; "$@"; else echo "would run: $*"; fi; }
answers() { [ "$(curl -s -o /dev/null -m 4 -w '%{http_code}' "$1" || true)" = "200" ]; }
free_gb() { nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | awk '{printf "%d", $1/1024}'; }
live_sessions() { # prints the number of live sessions a backend reports (0 when it does not answer)
  curl -s -m 5 "$1/api/live/sessions" 2>/dev/null | grep -o '"status":"live"' | wc -l | tr -d ' '
}

status() {
  for p in 9001 9002 9003 9010 9030 9041 9042 9043 9045; do
    if answers "http://127.0.0.1:$p/health"; then echo "up    :$p"; else echo "down  :$p"; fi
  done
  for p in 9020 9044; do
    if answers "http://127.0.0.1:$p/v1/models"; then echo "up    :$p (translation model)"; else echo "down  :$p (translation model)"; fi
  done
  echo "GPU free: $(free_gb || echo '?') GB"
  echo "live sessions: v0 $(live_sessions "$V0_API"), v1 $(live_sessions "$V1_API")"
  if answers "http://127.0.0.1:9044/v1/models"; then echo "mode: HQ window"; else echo "mode: normal"; fi
}

refuse_if_live() {
  local n0 n1
  n0="$(live_sessions "$V0_API")"; n1="$(live_sessions "$V1_API")"
  if [ "${n0:-0}" != "0" ] || [ "${n1:-0}" != "0" ]; then
    say "a Live session is running (v0: $n0, v1: $n1). Not switching: its translation would move to the hosted model mid-stream."
    [ "${FORCE:-0}" = "1" ] || exit 1
  fi
}

hq() {
  refuse_if_live
  say "HQ window: the small translation model goes down, the big one comes up"
  # The same way v0's own start script stops it: only the process that serves the small model.
  for pid in $(pgrep -f "vllm serve $SMALL_MODEL" || true); do do_ kill "$pid"; done
  if [ "$RUN" = "--run" ]; then
    for _ in $(seq 1 40); do pgrep -f "vllm serve $SMALL_MODEL" > /dev/null || break; sleep 1; done; sleep 3
    free="$(free_gb)"
    if [ "${free:-0}" -lt "$NEED_FREE_GB" ]; then
      say "only $free GB free after stopping the small model, $NEED_FREE_GB GB needed. Going back to normal."
      normal; exit 1
    fi
  fi
  do_ "${COMPOSE[@]}" --profile hq up -d big-llm
  do_ "${COMPOSE[@]}" --profile transcribe up -d transcribe
  if [ "$RUN" = "--run" ]; then
    for _ in $(seq 1 120); do answers http://127.0.0.1:9044/v1/models && break; sleep 5; done
    answers http://127.0.0.1:9044/v1/models || { say "the big model did not come up in 10 minutes. Going back to normal."; normal; exit 1; }
    log "hq start (free now: $(free_gb) GB)"
    say "HQ window open. Close it with: $0 normal --run"
  fi
}

normal() {
  say "normal: the big model goes down, the small one comes back"
  do_ "${COMPOSE[@]}" --profile hq --profile transcribe stop big-llm transcribe
  if answers http://127.0.0.1:9020/v1/models; then
    say "the small translation model already answers on :9020"
  else
    [ "$RUN" != "--run" ] || sleep 5
    do_ bash "$V0_ENGINE_DIR/start_llm.sh"
    if [ "$RUN" = "--run" ]; then
      for _ in $(seq 1 60); do answers http://127.0.0.1:9020/v1/models && break; sleep 5; done
      answers http://127.0.0.1:9020/v1/models || { say "WARNING: :9020 does not answer yet. v0 and v1 are translating through the hosted model. Check $V0_ENGINE_DIR/llm.log"; log "normal: 9020 NOT back"; exit 1; }
    fi
  fi
  [ "$RUN" != "--run" ] || log "hq end / normal (free now: $(free_gb) GB)"
  say "normal mode"
}

case "$MODE" in
  status) status ;;
  hq) hq ;;
  normal) normal ;;
  *) echo "usage: $0 status | hq [--run] | normal [--run]"; exit 2 ;;
esac
