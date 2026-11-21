#!/bin/bash
# Translation model of the all-GPU mode: Gemma 4 E4B behind an OpenAI-compatible endpoint on 127.0.0.1:9020.
# It needs half the card while it starts: at 0.40-0.42 it found no room for its cache (measured 22 Nov 2026), and it
# must start before the Indic-Mio servers, because its warm-up takes 5 GB more for a moment.
cd ~/voice_engine
for pid in $(pgrep -f "vllm serve ${LLM_MODEL:-google/gemma-4-E4B-it}"); do kill "$pid"; done
# The old server needs a moment to give its memory back; starting at once ran the card out of memory.
for i in $(seq 1 30); do pgrep -f "vllm serve ${LLM_MODEL:-google/gemma-4-E4B-it}" > /dev/null || break; sleep 1; done; sleep 3
nohup .venv_llm/bin/vllm serve ${LLM_MODEL:-google/gemma-4-E4B-it} --host 127.0.0.1 --port 9020 --served-model-name local \
  --gpu-memory-utilization ${LLM_GPU_SHARE:-0.5} --max-model-len 4096 --max-num-seqs 16 \
  --limit-mm-per-prompt '{"image":0,"audio":0,"video":0}' > llm.log 2>&1 &
echo started
