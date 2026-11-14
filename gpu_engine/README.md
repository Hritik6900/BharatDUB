# GPU voice engine for Live

Our own voice engine (IndicF5 on an A100) gives Live the speaker's copied voice without Gnani's
one-request-at-a-time limit. It is not a Gnani model; Studio and everything else still use Gnani.

On the GPU machine (`~/voice_engine` holds `voice_engine.py` and its venv `.venv2`):

```
python make_live_engine.py      # writes voice_engine_live.py: voice_engine.py + per-request speed and Opus output
bash start_live.sh              # three engine processes on ports 9001-9003 (they listen on localhost only)
python bench_mp.py 9001 9002 9003
```

On the PC that runs the backend:

```
.\gpu_engine\tunnel.ps1 -Key <ssh key> -Target <user@gpu-host>
# backend/.env:
GPU_VOICE_URL=http://127.0.0.1:9001,http://127.0.0.1:9002,http://127.0.0.1:9003
```

Empty `GPU_VOICE_URL` turns it off. If the tunnel or an engine is down, each line goes to the Gnani voice instead.
The voice is copied only on sessions created with "copy the voice on this stream" and its consent.

Measured 14 Nov 2026 (A100 40 GB, NFE 12, bf16): one line 0.91 s on the machine whatever its length; three lines
at once 1.19 s with three processes (2.26 s with three replicas in one process). From a laptop in India through
the tunnel (machine in Seoul): one line 1.2 to 1.7 s, three at once 1.6 to 1.9 s.
