#!/bin/bash
# One-time setup of the all-GPU mode on the GPU machine (run from ~/voice_engine, after setup_machine.sh).
# Adds two environments beside the voice engines' .venv2 and touches nothing of theirs:
#   .venv_stt  speech-to-text (faster-whisper + Silero VAD)       -> start_stt.sh, port 9030
#   .venv_llm  translation model server (vLLM, Gemma 4 E4B)       -> start_llm.sh, port 9020
# .venv_llm uses uv's own Python: vLLM compiles a small C module at start and needs Python.h, which the system
# Python on the machine did not have.
set -e
export PATH=$HOME/.local/bin:$PATH
cd "$(dirname "$0")"
[ -d .venv_stt ] || uv venv .venv_stt --python 3.10
uv pip install -p .venv_stt/bin/python torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
uv pip install -p .venv_stt/bin/python faster-whisper ctranslate2 transformers silero-vad fastapi "uvicorn[standard]" \
  python-multipart soundfile numpy huggingface_hub sentencepiece
[ -d .venv_llm ] || uv venv .venv_llm --python 3.12 --python-preference only-managed
uv pip install -p .venv_llm/bin/python vllm
.venv_llm/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('google/gemma-4-E4B-it')"
echo "done: bash start_stt.sh && bash start_llm.sh"
