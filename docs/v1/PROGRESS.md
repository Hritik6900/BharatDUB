# v1 progress log

One entry per phase: what changed, how to test, how to roll back, measured numbers.

## Setup (Part A), 23 Nov 2026

- Built in a second checkout on the laptop (branch `v1`); v0 runs from `main` in its own folder and was not edited.
- Baseline tag `v0-baseline` checked locally and on the remote: `80c36d8`.
- Commit hooks for this checkout only: a commit that names the assistant or its vendor, carries a zip or a file over
  10 MB is refused; such lines are removed from commit messages. Tested with a throwaway file.
- The ignore rules for the assistant's files are written as patterns, so the ignore file does not spell the names.
- Roll back: delete the `v1` branch checkout; nothing in v0 changed.

## Phase 1: discovery, 23 Nov 2026

- No code changed. `DISCOVERY.md` (map of v0, how each GPU server is called, data, eval, risks) and `PLAN.md`.
- Measured over HTTP only: voice engine 9001 reports 1.43 GB allocated and 82 voices held; Demucs 0.18 GB;
  Whisper 192 ms average decode. Per-process GPU memory needs a shell on the VM: `NEEDS_APPROVAL.md` item 1.
- v0 after this phase: all six GPU servers answer, backend 8010 and website 3000 answer.

## Phase 2: v1 scaffold beside v0, 23 Nov 2026

- **Changed:** v1 settings and flags in `backend/app/config.py` (all off), `app/v1/flags.py`, `app/v1/health.py`
  (`GET /api/v1/health`, `GET /api/v1/flags`), `app/v1/store_pg.py` (Postgres store, never run: approvals item 5),
  `docker-compose.v1.yml`, `Caddyfile.v1`, Dockerfiles, `.env.v1.example`, `scripts/v1/` (`run-local.sh`,
  `stop-local.sh`, `run-local.ps1`, `copy-voice-samples.sh`, `v0-check.sh`), website page `/health`.
- **Where it ran:** on the laptop. Backend 127.0.0.1:8110, website 127.0.0.1:3100, its own data folder, its own
  env file (keys copied from v0's, values never printed), the shared GPU servers through the existing forwards.
  The compose file was written but not run (no Docker here): approvals items 2 to 4.
- **Voice samples:** 14 sample files copied once from v0's voices folder into `<v1 data>/v0_voice_samples/`
  (source only read). Profiles were not copied: their consent records are in v0's store, which v1 does not read.
- **Measured, all flags off, one run each, the dense 24.9 s reel:**
  - Live (GPU engine, voice learned from the stream, Tamil + Bengali, sync mode, three loops): 34 phrases, first
    audio p50 2.5 s / p95 3.8 s, heard p50 4.6 s, 62% of phrases within 0.25 s of their moment, hold stayed 6 s,
    no errors, viewer chat translated back in 2.6 s.
  - Studio (hosted engine, stock voice, Tamil): done in 40.3 s (separate 6.1 s, segment 11.2 s, transcribe 3.1 s,
    translate 8.7 s, voice 9.2 s, render 1.6 s), MP4 and SRT written.
  - Status endpoint: six shared servers answer in 0.5-0.7 s each through the forwards, asked at the same time.
- **v0 after this phase:** `scripts/v1/v0-check.sh` all ok (backend, website, six GPU servers). No v0 session was
  live while the v1 runs were made (checked through v0's API first).
- **Test:** `cd backend && python -m pytest -q`; `curl http://127.0.0.1:8110/api/v1/health`; open
  `http://127.0.0.1:3100/health`.
- **Roll back:** stop the two v1 processes; nothing else depends on them.

## Phase 3: trace and numbers (`V1_TRACE`), 23 Nov 2026

- **Changed:** `app/v1/trace.py` (JSONL in `<DATA_DIR>/trace/trace-YYYYMMDD.jsonl` + Prometheus counters and
  histograms), `app/v1/metrics.py` (`GET /metrics`, `GET /api/v1/metrics/summary?hours=&session=`), website page
  `/metrics-ui`, four tests. In `live/pipeline.py` the flag adds marks to a phrase's timings (translation start,
  the voice engine's own time, which step fell back, characters spoken) and writes one record per phrase and
  language when the phrase is done; a viewer's `played` report is recorded with the phrase number. In
  `studio/runner.py` it writes one record per voiced line and one per run. With the flag off none of this runs.
- **A record holds:** trace id (session, phrase, language), the times of speech start and end, final transcript,
  translation start and end, first audio, last audio sent, the moment a viewer starts hearing it (server estimate),
  lateness against the video moment, providers, fallback yes/no per step, seconds of work on our GPU servers
  (the voice engine's own time, plus the translation call's time when our model answered).
- **Cost per minute:** GPU seconds x the GPU's hourly rate + hosted usage x its rates. The rates are settings and
  are 0 (not set), so the page shows no cost figure yet: the rates are a decision for the user.
- **Measured, one traced Live session** (GPU engine, voice from the stream, Tamil + Bengali, two loops of the reel,
  56 s): 44 records, 40 spoken, first audio p50 2.7 s, translation p50 0.55 s, 76% within 0.25 s and 89% within
  1 s of the video moment, 95% in the copied voice, no fallback, 46 s of GPU work reported for 0.74 stream minutes.
- **v0 after this phase:** `scripts/v1/v0-check.sh` all nine ok. Tests: 103 pass.
- **Test:** `V1_TRACE=true`, run a session, `curl "http://127.0.0.1:8110/api/v1/metrics/summary?hours=1"`, open
  `/metrics-ui`. **Roll back:** `V1_TRACE=false`.

## Phase 4: config-driven router (`V1_ROUTER`), 23 Nov 2026

- **Changed:** `backend/config/routing.yaml` (provider order per step, per mode `live` / `studio` / `studio_hq`
  and per engine, timeouts per step), `app/v1/router.py` (reads and checks the file, builds the provider objects,
  leaves out a provider whose address or key is not set), `app/v1/stages.py` (`transcribe()`, `translate()`,
  `speak()`, `separate()`, `diarize()`, `score()`: each walks its list with a timeout per provider and logs why it
  moved on; a job's voice stays with the provider that spoke its first line), clients for the new servers
  (`providers/stt_indic.py`, `providers/tts_gpu_v1.py`, `app/v1/qa.py`), `GET /api/v1/routing`.
  `providers/__init__.py` asks the router only when the flag is on; off, v0's fixed table answers as before.
- **Checked:** 17 tests. For five setups (nothing configured, hosted only, hosted + voice engine, everything,
  GPU machine without hosted keys), both engines and both modes, the shipped file builds the same provider
  objects as v0's table (same classes, same order of fallbacks). Bad files are refused; a broken file at run time
  falls back to v0's table instead of stopping the service.
- **Measured, router on, one Live run** (GPU engine, voice from the stream, Tamil + Bengali, two loops): same
  providers in the trace as with it off (hosted speech-to-text with ours behind it, our translation model with the
  hosted one behind it, our voice engine); first audio p50 2.4 s (2.7 s with it off in phase 3), 74% within 0.25 s
  and 85% within 1 s of the moment (76% / 89%), no fallback. One run each: inside what two equal runs differ by.
- **v0 after this phase:** all nine checks ok. Tests: 120 pass.
- **Test:** `python -m pytest tests/test_v1_router.py -q`; `curl http://127.0.0.1:8110/api/v1/routing`.
- **Roll back:** `V1_ROUTER=false`.

## Phase 5: Live changes, each behind its flag, 23 Nov 2026

- **Changed:** `app/v1/phrase.py` (dynamic phrase sizes, short-line merge, translation ahead: logic without I/O),
  `live/pipeline.py` (uses them only when their flags are on; late-line shortening; back-check of a dubbed line;
  a per-session glossary), `live/routes.py` (`glossary` on a new session; `V1_LIVE_STOCK_DEFAULT`),
  `providers/llm_local.py` (`V1_LLM_PREFIX_CACHE`: fixed rules first, temperature 0.1), `eval/v1/live.py` (the
  same recording through several backends in turn, mean and spread), `eval/v1/prefix.py`,
  `scripts/v1/ab-server.sh|ps1` (a second backend with chosen flags, own port and data folder). 16 tests.
- **Flags added beyond the first list:** `V1_ROUTER` (phase 4), `V1_LIVE_LATE_SHORTEN`, `V1_LIVE_BACKCHECK`,
  `V1_LLM_PREFIX_CACHE`. The 1.2x speed-up cap is the existing setting `LIVE_FIT_MAX_TEMPO=1.2`.
- **Fixed in a helper script:** `scripts/live_e2e.py` waited 90 s after every run because the once-a-second clock
  message counted as activity.

### Measured (dense 24.9 s reel, GPU engine, Tamil + Bengali, sync mode, hold 6 s; mean and range of 3 runs each, taken in turn)

Voice learned from the stream, three loops a run:

| | all flags off | `V1_PHRASE_DYNAMIC` | dynamic + ahead + prefix + late-shorten + 1.2x cap |
|---|---|---|---|
| First audio p50 | 2.34 s (2.27-2.40) | 2.37 s (2.28-2.41) | 2.46 s (2.42-2.50) |
| Within 0.25 s of the moment | 69.6% (68.8-70.1) | 64.5% (62.7-66.0) | 56.0% (52.4-59.6) |
| Within 1 s | 83.3% (81.2-85.0) | 79.8% (78.9-81.4) | 75.6% (68.3-79.7) |
| Phrases a run | 36.7 | 32 | 33.3 |
| Skipped as too late | 4.7 (3-6) | 4 (1-6) | 1.7 (0-3) |
| At the speed limit | 20 | 18 | 25.3 |
| First word of the session to first audio | 7.2 s (6.4-8.0) | 7.2 s (6.3-7.8) | 7.6 s (6.4-8.7) |

Stock voices (nothing to learn first), two loops a run:

| | all flags off | `V1_PHRASE_DYNAMIC` |
|---|---|---|
| First word of the session to first audio | 5.9 s (4.9-6.5) | 4.1 s (4.0-4.4) |
| First audio p50 | 5.1 s (2.6-6.6) | 5.2 s (2.7-6.6) |
| Within 1 s | 58.3% (45.5-81.6) | 56.9% (43.5-81.6) |

What the numbers say:

- **Dynamic phrases:** the short first phrase brings the first dubbed audio 1.7 s earlier when a voice is ready at
  the start (stock, or a streamer's recorded voice; measured with stock). With a voice learned from the stream
  the first audio waits for the voice (about 7 s) and nothing is gained. The longer later phrases (8-12 words)
  cost timing on this reel: 5 points fewer on time, outside the spread of the runs. This reel has no one- or
  two-word lines, so the merge was not exercised (0 joined): its effect is not measured.
- **Translation ahead** never produced a used translation in 5 runs: 4-6 starts a run, all dropped. Three of four
  were the speaker carrying on; one was a final that kept fewer words than the partial. Partials arrive about
  470 ms apart, so a pause is only certain after about 700 ms, which is when the final arrives anyway. No gain
  with this speech-to-text; it costs 4-6 extra translation calls a language a minute.
- **Fixed rules first:** no gain. The server's prefix cache was already on (vLLM 0.34.0) and already held the
  prompt for each word limit: 61.4% of prompt tokens came from the cache with the flag off and on (40 calls each),
  call time p50 379 ms against 420 ms (noise).
- **Late-line shortening** works as built: 1-3 lines a run were said shorter and skips fell from 4.7 to 1.7 a run,
  but in a bundle whose timing was worse, so its own effect on timing is not separated.
- **1.2x cap:** more phrases at the limit (25 against 20), as expected from a lower limit.
- **Back-check** and **stock default** were not measured in a run: the back-check has no scorer until the QA
  server exists (it does nothing without one); stock default is covered by a test.
- **Targets:** first audio p50 is 2.3-2.5 s here against the 1.8 s target, and on time is 56-70% against 90%.
  None of these flags moves either. v0's own measurement put first audio at 1.8 s with the backend on the GPU
  machine (no tunnel in the path), which is `NEEDS_APPROVAL.md` item 3 and was not repeated here.
- **Not measured:** words heard back per run (it needs a hosted call per line), a person at a microphone, a
  stream with short lines.

- **v0 after this phase:** all nine checks ok; no v0 session was live during the runs. Tests: 155 pass.
- **Test:** `python -m pytest tests/test_v1_phrase.py -q`; the comparison:
  `scripts/v1/ab-server.sh 8111 base` and `... 8112 dynamic V1_PHRASE_DYNAMIC=true`, then `python -m eval.v1.live`.
- **Roll back:** each flag off. Recommended now: all of these off, except `V1_PHRASE_DYNAMIC` for sessions that
  start with a ready voice if the earlier first audio is worth 5 points of on-time (a decision for the user).
