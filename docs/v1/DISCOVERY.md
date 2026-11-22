# v1 discovery: what v0 is and how v1 can sit beside it

Read from the code at `80c36d8` and from the running setup on 23 Nov 2026. No code was changed for this file.

Where this was done: on the laptop, in a second checkout of the repository (branch `v1`), not on the GPU VM.
Everything that needs a shell on the VM is listed in `NEEDS_APPROVAL.md`.

## 1. Processes and ports

| What | Where | Port | Code |
|---|---|---|---|
| Website (Next.js) | laptop | 3000 | `web/` |
| Backend (FastAPI, one process) | laptop | 8010 | `backend/app/` |
| IndicF5 voice engine x3 | VM, 127.0.0.1 only | 9001-9003 | `gpu_engine/voice_engine_live.py` |
| Demucs | VM, 127.0.0.1 only | 9010 | `gpu_engine/sep_engine.py` |
| Gemma 4 E4B on vLLM (`google/gemma-4-E4B-it`, served as `local`, context 4096) | VM | 9020 | `gpu_engine/start_llm.sh` |
| Whisper-Hindi2Hinglish-Apex | VM | 9030 | `gpu_engine/stt_engine.py` |
| Indic-Mio (stopped) | VM | 9040, 9021 | `gpu_engine/mio_engine.py` |

The laptop reaches 9001-9040 through SSH port forwards opened by `gpu_engine/tunnel.ps1` (one connection per kind
of traffic). The engines listen on the VM's loopback only, so a container on a bridge network cannot reach them:
a v1 backend container needs host networking.

## 2. How the backend calls each GPU server

All calls go through `backend/app/providers/`; pipelines never open HTTP connections themselves.

| Server | Provider | Call | Payload | Timeout, retry |
|---|---|---|---|---|
| Voice 9001-9003 | `tts_gpu.GpuVoice` | `POST /ref` | multipart `session_id`, `ref_text`, `audio` (wav) | 20 s, 1 retry |
| | | `POST /tts` | json `session_id, text, lang, fmt(mp3), speed, nfe` -> audio, headers `x-sample-rate`, `x-format`, `x-synth-ms` | `GPU_VOICE_TIMEOUT_S` 6 s, no retry |
| | | `GET /health` | `{ok, nfe, bf16, batched_guidance, voices, gpu_gb}` | 3 s |
| Demucs 9010 | `studio/stages/separate._separate_gpu` | `POST /separate` | multipart `audio` (flac) -> stems | 180 s, CPU fallback |
| Gemma 9020 | `llm_local.LocalLLM` (an `OpenAILLM`) | `POST /v1/chat/completions` | OpenAI chat, temperature 0.2-0.3 | 20 s for a live line, 1 retry |
| Whisper 9030 | `stt_gpu.GpuSTT` | `POST /stt` | multipart audio + `lang` | 30 s |
| | | `WS /stream?min_silence_ms=&partial_interval_ms=` | 1024-byte PCM16 frames, `{"type":"commit"}` | open 4 s |
| | | `GET /health` | `{ok, model, streams, decodes, decode_ms_avg}` | 3 s |

A line goes to the least busy voice engine; a voice sample is sent to all three. The engine set is one comma
separated setting (`GPU_VOICE_URL`), so pointing v1 at another voice server is configuration only.

Provider selection is `providers/__init__.py`: `engine_of()` resolves `cloud` or `gpu` per Live session or Studio
job, and `_stt/_llm/_tts/_gpu_voice(engine)` build the provider with its fallback:

| Stage | `cloud` engine | `gpu` engine |
|---|---|---|
| Speech-to-text | Prisma (Gnani) | Prisma first, Whisper 9030 behind it (`GPU_STT_FIRST=hosted`); `gpu` reverses the order |
| Translation | Gemini (OpenAI-compatible endpoint) | Gemma 9020 first, Gemini behind it |
| Voice, copied, Indian languages | IndicF5 9001-9003 when `GPU_VOICE_URL` is set, else Gnani clone | IndicF5 with the short-line guard |
| Voice, stock and English | Gnani Timbre | Gnani Timbre |
| Separation | Demucs 9010 when `GPU_SEPARATE_URL` is set, else CPU | same |

## 3. Code paths

**Live** (`live/routes.py`, `live/pipeline.py`, `live/assembler.py`): `WS /ws/ingest/{sid}` feeds PCM into
`LivePipeline.feed`; `_stt_loop` streams it to the speech-to-text provider; `_on_stt` cuts phrases from partials
(`Phraser`, 6-12 words at a clause boundary) or takes the final's tail; `_dispatch` starts one translation task per
language at once (`_translate`, captions in order); `_worker` per language waits for the voice turn and calls
`_speak` (GPU voice, else the hosted stream), which fits the audio (`live_fit*`), publishes it on the bus and stores
the timings. `_chunk_done` writes one `live_chunks` row per phrase with every timing mark. `WS /ws/watch/{sid}`
sends captions and audio; a viewer reports `{"type":"played","late_ms"}` back.

**Studio** (`studio/runner.py`, `studio/stages/`): `POST /api/jobs` -> ingest -> extract -> separate -> segment ->
transcribe -> (voice from the video, with consent) -> per language: translate, voice per line, fit, mix, render.
Stage cache under `<data>/cache/<stage>/`, content addressed. A job's engine is kept in its `meta.json` and set in
a context variable for the task that runs it. Progress is sent as server-sent events.

**Streamer** (`streamer/routes.py`, `streamer/voice_ref.py`): profile, recorded voice with consent (Demucs, three
7 s cuts, each transcribed and scored), then a Live session with `streamer_id`.

## 4. Settings and data

- Settings: `backend/app/config.py` (pydantic settings, read from `backend/.env`); every tunable is an environment
  variable. Keys: `GNANI_API_KEY`, `LLM_API_KEY`. The web reads `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_WS_BASE` at
  build time.
- Store: Supabase is not configured on the running setup. `db.get_store()` returns `LocalStore`, one JSON file
  (`<DATA_DIR>/local_db.json`, tables: jobs, segments, translations, renders, voice_profiles, glossary_terms,
  live_sessions, live_chunks, chat_messages, streamers), held in memory by the one backend process and written on
  every change. Two processes on the same file overwrite each other.
- Files: `<DATA_DIR>/jobs/<id>/`, `<DATA_DIR>/cache/`, `<DATA_DIR>/voices/` (voice samples and engine cuts).
  `DATA_DIR` empty = `backend/data` of that checkout.
- Voice profiles are rows in the store (`consent_at`, `embedding`, `ref_path`, `ref_text`, `ref_score`); the sample
  files are in `<DATA_DIR>/voices/`.

## 5. What `backend/eval/` holds

`eval/run.py` writes `eval/results.csv` from stored runs: word error rate on `eval/clips/*.wav` + `.txt` (the folder
is empty), Studio turnaround and slot fit from finished jobs in the store, Live first-audio and heard p50/p95 from
`live_chunks`. `eval/gaming/` is empty. The harder Live and voice checks were scripts outside the repository.
Helper scripts in `backend/scripts/`: `live_e2e.py` (replays a file through a session at real-time speed, with
viewers), `live_quality.py` (words heard back), `live_player_sim.py`, `dub_file.py`, `smoke.py`.

## 6. GPU memory

Only what the engines report over HTTP could be read from here (`torch` allocations, not the process totals that
`nvidia-smi` shows):

| Server | Reported | Note |
|---|---|---|
| Voice 9001 | 1.43 GB allocated, 82 voices held, 12 steps, bf16, batched guidance | each of the three processes; process total is higher |
| Demucs 9010 | 0.18 GB allocated | |
| Whisper 9030 | not reported; 192 ms average decode over 2147 decodes | |
| Gemma 9020 | not reported | started with a memory share of 0.45 of the card |

Earlier measurements (project spec, section 21): all engines together 34.7 of 40 GB with Indic-Mio loaded, about
33.7 GB with it stopped. The per-process table from `nvidia-smi` is deferred (needs a shell on the VM).

## 7. Risks found

1. **One hosted speech and voice account, one request at a time, shared by v0 and v1.** A v1 test that uses the
   hosted services while a v0 stream is live makes both wait or fail. v1 runs are done only when no v0 session is
   live (checked through v0's own API before each run).
2. **One GPU through one tunnel is one stream** (measured in v0: a second session halved the on-time share). Same
   consequence: no v1 Live run beside a v0 stream.
3. **The Whisper server on 9030 is a Hindi/Hinglish model.** It cannot hear Tamil, Bengali or Punjabi speech back,
   so it cannot be the back-check for a dubbed line. Back-check needs a multilingual model (the planned QA server)
   or the hosted Prisma, which shares the one-request limit.
4. **v0's engines bind 127.0.0.1.** A v1 backend in a container needs `network_mode: host`.
5. **Voice profiles live in v0's JSON store, which v1 must not read.** Only the sample files can be copied; a
   profile needs its consent record, so voices are recorded again in v1 (with consent) rather than imported.
6. **`LocalStore` is one process, one file.** v1 gets its own file under its own data folder; the Postgres store
   is new code and could not be run here (no database on the laptop).
7. **No Docker on the laptop**, and whether the VM has Docker is not known. The compose file is written but was not
   run; a script that starts v1 without containers exists beside it.
8. **Speculative translation and N-best voice multiply calls.** Both are bounded (one speculation per pause; extra
   voice versions only for lines that fail the check).
9. **The three voice engines hold every voice ever sent** (82 on one engine) until restarted.
