# BharatDb v1: architecture

v1 is built beside the running product (v0) and must never break it. This file holds the context v1 starts from, the design, and the build rules.

## CONTEXT — what exists today (v0)

- **Laptop:** Next.js :3000 (`web/`), FastAPI :8010 (`backend/`), data in local JSON (check whether
  `supabase/` is used), no login, SSH tunnel to the VM. Windows dev script `dev.ps1`.
- **VM GPU servers (`gpu_engine/`):** IndicF5 ×3 :9001–9003 (~12 GB), Demucs :9010 (~1.4 GB),
  Gemma 4 vLLM :9020 (~18 GB), Whisper :9030 (~2.5 GB). Indic-Mio off.
- **`providers/` layer** in the backend: every AI call goes through it, each with a backup.
  Hosted: Gnani (Prisma STT, Timbre stock voice, Vachana clone), Gemini (translation).
- **Engine button:** Standard (default) vs GPU engine. `GPU_STT_FIRST=gpu` moves STT to Whisper.
- **Studio (/studio):** upload ≤3 min + ownership tick → ffprobe → ffmpeg 44.1 kHz WAV → Demucs →
  Silero VAD ≤25 s → transcribe → translate (all languages at once) → voice (clone or stock) →
  fit (≤1.35x → shorten → regenerate) → mix (music −6 dB under speech) → MP4 + SRT + "AI-dubbed" label.
  Per-stage cache; editing one line re-runs only steps 7–10. Clone needs consent (else 403). SSE progress.
- **Live (/live + /watch/[id]):** tab/mic 16 kHz PCM + video time over `WebSocket /ws/ingest` →
  STT partial/final every ~0.3–0.5 s → phrase 6–12 words at clause breaks → voice learning (~7 s sample,
  ready ~9 s; stock voice until then) → translate all languages, word limit by speaker rate, captions sent
  immediately → TTS only for languages with viewers (IndicF5 for Indian copied voice; Timbre for
  English/stock; GPU engine adds short/swallowed-line guard) → fit (trim silence, ≤1.3x, skip >8 s late) →
  `WebSocket /ws/watch`. Viewer delays video 6 s, plays each phrase at its video time, original at 18%,
  chat translated back.
- **Streamer (/streamer):** enrollment (consent sentence → Demucs → three 7 s cuts → Prisma text → best cut →
  Gnani embedding + IndicF5 sample) → go-live wizard → Live pipeline with own voice from first sentence;
  YouTube offset slider 0–40 s.
- **Measured:** Live first audio p50 2.3–2.9 s; on-time 72–95% by engine; hard-audio key words Prisma 73/80
  vs Whisper 49/80; Gemma translation 0.4–0.6 s vs Gemini 0.85–0.96 s; Studio back-check 91–93% (GPU)
  vs 74–76% (Standard).
- **Existing docs to read in Discovery:** README.md, SPEC.md, FRONTEND.md, STREAMER_MODE*.md,
  LIVE_TEST_REPORT*.md. `backend/eval/` already exists — reuse and extend it.

## DESIGN — what v1 is

**Goal:** best-quality pitch samples + stable demo + real numbers, with code shaped for production later.

**Targets:** Studio back-check ≥ 96% (from 91–93%); Studio speed-up ≤ 1.15x; Live first audio p50 ≤ 1.8 s;
Live on-time ≥ 90% with Prisma; hard-audio key words ≥ 73/80; after VM reboot everything warm + green in 5 min.

**Layout on the VM:** Caddy (HTTPS + demo password) → web :3100 + backend :8110 (one async FastAPI process:
api, live, studio, router modules) → Redis (queue/live state) + store (`V1_STORE`) → shared v0 GPU servers
(9001–9030, call only) + new v1 servers (9041–9045) → hosted vendors (Prisma, Gemini, Bulbul/Gnani backups).

**Port map for new v1 servers:** :9041 TTS server (one IndicF5 copy + dynamic batching, same API as v0's),
:9042 Maya 2 Native (streaming TTS, cloning), :9043 Indic Transcribe Core (Bodhan), :9044 big LLM for
Studio HQ (larger Gemma 4 variant, 4-bit AWQ/GPTQ on vLLM — A100 has no native FP8), :9045 QA
(back-check STT + speaker similarity, e.g. ECAPA/WavLM).

**GPU profiles:** *Live/normal* = v0 servers as today (~34 GB). *HQ window* (`gpu-mode.sh hq`, user runs it)
= stop Gemma :9020 (v0 falls back to Gemini automatically), load :9044 (+ :9043); `normal` reverses.
Studio HQ uses phase batching: all queued jobs do phase A, then B (big LLM loaded once), then C.

**Model stack:** VAD Silero (CPU). Separation Demucs (shared :9010); test RoFormer vocal model later.
Diarization pyannote (licence check). STT Live: Prisma realtime, Whisper backup; Studio HQ: Prisma +
Indic Transcribe, LLM resolves disagreements. Translation Live: Gemma 4 (:9020); Studio HQ: big LLM with
full-transcript context; Gemini fallback. TTS: IndicF5 (+ Maya 2 candidate); Bulbul/Timbre stock fallback.

## RULES (v1 build rules)

1. v0 must keep working at all times. Never modify, restart, stop or reconfigure anything on ports
   3000, 8010, 9001–9003, 9010, 9020, 9030, 9040 (9040 = v0 Indic-Mio, currently off). v1 may only CALL the GPU servers on 9001–9030 over HTTP.
2. Never edit v0-only code: `gpu_engine/` (v0 GPU servers), `dev.ps1`. New v1 model servers go in
   `gpu_engine_v1/`. v1 work happens on the `v1` branch directly in `backend/` and `web/`.
   v0 keeps running from `main` on the laptop.
3. Never read from or write to v0 data (`backend/data/`, `backend/data-mock/`, v0's JSON, v0 media/voice
   folders). v1 data lives only in `/srv/bharatdb-v1/data/`. Copy voice samples from v0 once; never write back.
4. v1 ports: web :3100, backend :8110, new model servers :9041–9045. Docker Compose project `bharatdb-v1`.
   Never bind 3000, 8010 or 9001–9040.
5. Every new behaviour goes behind a flag in v1's `.env`, default OFF:
   `V1_TRACE, V1_PHRASE_DYNAMIC, V1_SPEC_TRANSLATE, V1_TTS_SERVER, V1_TTS_MAYA, V1_LIVE_STOCK_DEFAULT,
   V1_STUDIO_HQ, V1_FIT_115, V1_STORE=json|postgres`.
6. GPU memory: v0 uses ~34 GB; ~6 GB free, and v0 needs headroom for spikes. Only load a new model on the
   GPU if `nvidia-smi` shows (free GB − model GB) ≥ 4 GB. Otherwise DEFER.
7. Never run `gpu-mode.sh hq|normal` or stop/start Gemma :9020 or any v0 server. Write the script, dry-run
   with `echo` only; the real run is DEFERRED.
8. No sudo, system packages, firewall, DNS, Caddy domain or GCP changes. DEFER them.
9. Never put API keys in code or commits. Keys only in v1's `.env` (git-ignored). Copy needed keys from
   `backend/.env` into v1's `.env`; never print them in logs.
10. **DEFER rule (auto mode).** When something is forbidden above or needs the user's decision (licence
    unclear, weights > 5 GB, GPU memory insufficient, blocked by permissions): append to
    `docs/v1/NEEDS_APPROVAL.md` — what, why, exact commands, expected GPU GB, rollback. Skip it, mark
    dependent work "blocked on approval", and continue with everything else. Never try to work around a
    blocked command.
11. After any change: confirm v0 still works (one v0 Studio job + one v0 Live session against the shared
    GPU servers, or v0 health endpoints if a full run is not possible). If v0 breaks: revert your last change
    immediately, log it in PROGRESS.md, continue elsewhere.
12. Model sizes, licences and ports in this file are estimates — verify before relying on them
    (especially Bodhan Indic Transcribe, pyannote, Maya 2 Native).
13. Nothing committed may mention the AI assistant or its vendor: no such words in files, code comments,
    docs, commit messages, trailers or PR text. Its config files (the assistant settings folder, the assistant rules file and the master instructions file)
    stay git-ignored. Never commit zips, model weights, media, or files > 10 MB. The pre-commit and
    commit-msg hooks enforce this; never bypass them (`--no-verify` is forbidden).
