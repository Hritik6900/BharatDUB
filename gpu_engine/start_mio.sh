#!/bin/bash
# Second voice engine of the GPU engine: Indic-Mio. Two processes, both on 127.0.0.1:
#   9021  the language model that writes speech tokens (vLLM, about 2.9 GB)
#   9040  mio_engine.py: speaker embedding + codec, the same /ref and /tts calls as voice_engine_live.py
# One-time: uv venv .venv_mio --python 3.12 --python-preference only-managed, then torch (cu124) and
#   uv pip install "miocodec @ git+https://github.com/Aratako/MioCodec@main" fastapi "uvicorn[standard]" httpx soundfile python-multipart
# Order on a 40 GB card that also holds the other engines: first `LLM_GPU_SHARE=0.45 bash start_llm.sh` and wait
# until it answers (its warm-up needs about 5 GB for a moment), then this script. A share of 0.07 here left the
# model no room beside the translation model; 0.10 works.
cd "$(dirname "$0")"
if ! curl -s -m 2 127.0.0.1:9021/v1/models > /dev/null; then
  nohup .venv_llm/bin/vllm serve SPRINGLab/Indic-Mio --host 127.0.0.1 --port 9021 --served-model-name mio \
    --max-model-len 1024 --gpu-memory-utilization ${MIO_GPU_SHARE:-0.10} > mio_llm.log 2>&1 &
fi
for pid in $(pgrep -f "uvicorn mio_engine:app"); do kill "$pid"; done
sleep 1
nohup .venv_mio/bin/python -m uvicorn mio_engine:app --host 127.0.0.1 --port 9040 > mio.log 2>&1 &
echo "mio engine starting on 9040 (logs: mio.log, mio_llm.log)"
