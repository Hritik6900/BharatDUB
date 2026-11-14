#!/bin/bash
# Runs ON the GPU machine: (re)start the three Live voice engine processes on ports 9001-9003.
# Separate processes really work in parallel (3 lines at once: 1.2 s; replicas in one process: 2.3 s).
# The original engine on port 9000 is not touched.
cd ~/voice_engine || exit 1
unset LD_LIBRARY_PATH
pkill -f 'voice_engine_live:app' 2>/dev/null
sleep 2
for p in 9001 9002 9003; do
  NFE=${NFE:-12} REPLICAS=1 nohup .venv2/bin/python -m uvicorn voice_engine_live:app --host 127.0.0.1 --port $p \
    > /tmp/voice_engine_$p.log 2>&1 &
done
for i in $(seq 1 60); do
  n=0
  for p in 9001 9002 9003; do curl -s -m 2 http://127.0.0.1:$p/health > /dev/null && n=$((n + 1)); done
  [ "$n" = 3 ] && break
  sleep 3
done
echo "engines up: $n"
