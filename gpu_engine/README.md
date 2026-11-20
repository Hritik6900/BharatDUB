# GPU voice engine for Live

Our own voice engine (IndicF5 on an A100) gives Live the speaker's copied voice without Gnani's
one-request-at-a-time limit. It is not a Gnani model; Studio and everything else still use Gnani.

On a fresh GPU machine (everything goes under `~/voice_engine`, no root needed):

```
mkdir -p ~/voice_engine     # copy this folder's .sh and .py files into it
bash setup_machine.sh       # uv, Python env `.venv2`, PyTorch (CUDA), the IndicF5 code
.venv2/bin/hf auth login    # once: the model is gated; accept its terms on huggingface.co/ai4bharat/IndicF5 first
bash start_live.sh          # three engine processes on ports 9001-9003 (localhost only), under CUDA MPS
bash start_sep.sh           # Studio separation on port 9010
```

`voice_engine_live.py` is the whole engine (written again on 20 Nov 2026: the first one, and `voice_engine.py` that
`make_live_engine.py` patched, were lost with the first machine). After a machine restart only the two `start_*.sh` are needed.

**MPS matters.** Without it the three processes take turns on the GPU. Measured 20 Nov 2026 on a GCP A100: one line
1.0 s, two at once 2.1 s, three at once 3.2 s; with MPS 0.9 s / 0.95 s / 1.1 s. `start_live.sh` starts the MPS daemon as
the login user (`MPS=0` to skip). bf16 is about 10% faster than fp32 with clean output; fp16 gave NaN.

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

## Studio: Demucs on the GPU

```
bash start_sep.sh        # on the GPU machine: installs Demucs beside the voice venv (not inside it), port 9010
# backend/.env on the PC (the tunnel script forwards 9010 too):
GPU_SEPARATE_URL=http://127.0.0.1:9010
```

Measured 20 Nov 2026 on the second machine: 60 s of audio in 4.0 to 4.8 s through the tunnel (1.5 s on the GPU).
Measured 15 Nov 2026 on the first machine, 60 s of audio: 11.5 to 13.8 s through the tunnel (1.5 s on the GPU, the rest is sending
2.4 MB and receiving 4.3 MB of FLAC), against 38.9 s on the laptop CPU. The stems match the CPU result
(difference 40 dB below the signal). On any failure the backend separates on the CPU as before.
