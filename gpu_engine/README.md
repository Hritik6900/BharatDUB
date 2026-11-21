# GPU voice engine for Live

Our own voice engine (IndicF5 on an A100) gives Live the speaker's copied voice without Gnani's
one-request-at-a-time limit. Speech-to-text, stock voices and Studio's copied voice still come from Gnani.

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

**Speed, measured 21 Nov 2026** (bf16, 12 steps): one line 439 ms on the GPU, 0.79 s from the laptop; three at once
0.97 s. Both halves of the guidance run as one batch (`CFG_BATCH=1`, about twice as fast as the library's two
passes) and lines come back as MP3 (30 ms to make; Opus took 144 ms). `python bench_cfg.py ref.wav "its words"`
repeats the comparison.

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

## All-GPU mode: speech-to-text and translation on the same machine (21 Nov 2026)

A second engine beside the hosted one, chosen per Live session and per Studio job with the "Engine" button on the
site (`engine: "gpu"` on `POST /api/live/sessions` and `POST /api/jobs`). The default is the hosted engine and it is
not touched. On the GPU engine the backend also takes speech-to-text and translation from this machine, so a phrase
makes no trip to a hosted service; the hosted ones stay as the fallback when their keys are set.

| Part | Model | Licence | Port | Memory |
|---|---|---|---|---|
| Speech-to-text, live partials (`stt_engine.py`) | Oriserve/Whisper-Hindi2Hinglish-Apex, CTranslate2 float16 | Apache-2.0 | 9030 | about 2 GB |
| Translation (`start_llm.sh`, vLLM) | google/gemma-4-E4B-it, bf16 | Apache-2.0 | 9020 | about 19 GB (`LLM_GPU_SHARE`, 0.5 of the card) |
| Voice (`voice_engine_live.py`, as before) | ai4bharat/IndicF5 | MIT tag, commercial use unanswered | 9001-9003 | 12 GB |

```
bash setup_gpu_mode.sh                 # once: two environments beside .venv2 (.venv_stt, .venv_llm) and the models
bash start_stt.sh && bash start_llm.sh # after every restart of the machine (the model server needs about 2 minutes)
# backend/.env on the PC (tunnel.ps1 forwards 9020 and 9030 too). These two lines put the button on the site:
GPU_STT_URL=http://127.0.0.1:9030
GPU_LLM_URL=http://127.0.0.1:9020/v1
# AI_MODE=gpu would make it the default for every session; left out, a session uses it only when it is picked.
```

All five engines together use 34.7 of 40 GB; one stream in two languages keeps the GPU 36% busy on average.

What to know:
- The speech-to-text model hears **Hindi and Hinglish only** and writes them in Latin letters ("ise ham machine mein
  dedh ghante pakaate hain"). Other source languages, and hearing a dubbed line back, go to the hosted service.
  The same reel, another Whisper (large-v3-turbo) wrote wrong words where this one matched the hosted transcript.
- Whisper does not stream: while somebody speaks the utterance is decoded again every 0.3 s (120 ms a decode), a word
  counts as settled once two decodes agree, and an utterance with no pause is closed after 9 s.
- The voice engine wants its sample's text in Devanagari: with the Latin text the same lines were heard back 61% /
  72% (Bengali / Tamil) against 91% / 87%. The translation model rewrites the sample's text once per sample (0.7 s).
- The translation model has its own short prompt (`providers/llm_local.py`). On the hosted prompt it left English
  words in Latin letters in 7-10 of 14 lines, which the voice engine cannot read; on its own prompt 0 of 42.
- There is no stock voice and no English on the GPU: both stay with the hosted voice service.
- SraVaani-0.5-live (MIT, a real streaming model) and the Gemma 3 models are gated on Hugging Face and this
  machine's login has no access; they were not tried.
