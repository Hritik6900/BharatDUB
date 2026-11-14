#!/bin/bash
# Runs ON the GPU machine: install Demucs beside (not inside) the voice engine's venv, then start the
# separation engine on port 9010. Safe to run again.
cd ~/voice_engine || exit 1
unset LD_LIBRARY_PATH
PKGS=~/voice_engine/demucs_pkgs
if [ ! -d "$PKGS/demucs" ]; then
  # --no-deps: torch and torchaudio come from .venv2 and must not be touched or downloaded again
  .venv2/bin/pip install -q --target "$PKGS" --no-deps demucs dora-search julius einops openunmix lameenc \
    omegaconf antlr4-python3-runtime==4.9.3 treetable retrying submitit cloudpickle diffq 2>&1 | tail -3
fi
pkill -f 'sep_engine:app' 2>/dev/null
sleep 1
PYTHONPATH="$PKGS" nohup .venv2/bin/python -m uvicorn sep_engine:app --host 127.0.0.1 --port 9010 \
  > /tmp/sep_engine.log 2>&1 &
for i in $(seq 1 60); do
  curl -s -m 2 http://127.0.0.1:9010/health > /dev/null && break
  sleep 3
done
curl -s -m 3 http://127.0.0.1:9010/health || { echo "separation engine did not start:"; tail -15 /tmp/sep_engine.log; }
echo
