#!/bin/bash
# Speech-to-text engine of the all-GPU mode on 127.0.0.1:9030. Run on the GPU machine from ~/voice_engine.
cd "$(dirname "$0")"
mkdir -p models
if [ ! -d models/apex-ct2 ]; then
  .venv_stt/bin/ct2-transformers-converter --model Oriserve/Whisper-Hindi2Hinglish-Apex --output_dir models/apex-ct2 \
    --quantization float16 --copy_files tokenizer.json preprocessor_config.json
fi
for pid in $(pgrep -f "uvicorn stt_engine:app"); do kill "$pid"; done
sleep 1
STT_MODEL=${STT_MODEL:-models/apex-ct2} nohup .venv_stt/bin/python -m uvicorn stt_engine:app --host 127.0.0.1 --port 9030 > stt.log 2>&1 &
echo "stt engine starting on 9030 (log: stt.log)"
