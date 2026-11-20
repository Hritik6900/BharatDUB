#!/bin/bash
# Runs ON a fresh GPU machine as the login user: Python environment, PyTorch, the IndicF5 code.
# After it: `.venv2/bin/hf auth login` once (the model is gated), then start_live.sh and start_sep.sh.
# Everything goes under ~/voice_engine and ~/.local: no sudo, no system
# packages, no shell profile edits. Safe to run again.
set -e
mkdir -p ~/voice_engine
cd ~/voice_engine
unset LD_LIBRARY_PATH

# uv: one user-space binary that makes the Python environment (the machine has no pip and no venv package).
if [ ! -x ~/.local/bin/uv ]; then
  curl -LsSf https://astral.sh/uv/install.sh | env INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null 2>&1
fi
UV=~/.local/bin/uv
echo "uv: $($UV --version)"

if [ ! -x .venv2/bin/python ]; then
  $UV venv --seed --python 3.10 .venv2 2>&1 | tail -2
fi
PY=.venv2/bin/python
t0=$(date +%s)
$UV pip install -q --python $PY torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124 2>&1 | tail -3
$UV pip install -q --python $PY "numpy<2" soundfile fastapi "uvicorn[standard]" python-multipart pyyaml tqdm 2>&1 | tail -3
echo "packages installed in $(( $(date +%s) - t0 )) s"
$PY -c "import torch, torchaudio, soundfile; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0)); print('libsndfile', soundfile.__libsndfile_version__, '| opus', 'OPUS' in soundfile.available_subtypes('OGG'))"
du -sh ~/voice_engine | awk '{print "voice_engine folder:", $1}'
$UV pip install -q --python $PY "git+https://github.com/ai4bharat/IndicF5.git" 2>&1 | tail -6
$UV pip install -q --python $PY "numpy<2" huggingface_hub 2>&1 | tail -2
echo "installed in $(( $(date +%s) - t0 )) s"
