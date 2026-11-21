#!/bin/bash
# Translation model of the all-GPU mode: Gemma 4 E4B behind an OpenAI-compatible endpoint on 127.0.0.1:9020.
cd ~/voice_engine
pkill -f "vllm serve" 2>/dev/null; sleep 2
nohup .venv_llm/bin/vllm serve ${LLM_MODEL:-google/gemma-4-E4B-it} --host 127.0.0.1 --port 9020 --served-model-name local \
  --gpu-memory-utilization ${LLM_GPU_SHARE:-0.5} --max-model-len 4096 --max-num-seqs 16 \
  --limit-mm-per-prompt '{"image":0,"audio":0}' > llm.log 2>&1 &
echo started
