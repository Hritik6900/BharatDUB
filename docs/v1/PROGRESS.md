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
