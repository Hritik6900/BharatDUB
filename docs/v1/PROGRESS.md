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

## Phase 6: new model servers (`gpu_engine_v1/`), 23 Nov 2026

- **Changed:** `gpu_engine_v1/`: `tts_server.py` (:9041, one IndicF5 that batches lines; any batch error speaks
  those lines one at a time the way v0's engine does, and three errors switch batching off), `maya_server.py`
  (:9042), `transcribe_server.py` (:9043), `qa_server.py` (:9045: hear a line back, speaker similarity,
  diarization; CPU by default), a vLLM service for the big translation model (:9044), one Dockerfile per server,
  `docker-compose.models.yml` with a profile per server, `README.md`. `scripts/v1/gpu-mode.sh`
  (`status | hq | normal`, prints only unless `--run`). `docs/v1/MODELS.md` (what each model is, licence, size).
- **Nothing was loaded on the GPU.** About 6 GB is free beside v0 and the rule keeps 4 GB free, so no model over
  2 GB may load; every load is in `NEEDS_APPROVAL.md` (items 6-12) with its commands, expected memory and
  rollback. Each server has a stub mode (`V1_STUB=1`, no model, no GPU): the four stubs were run in-process and
  called through the backend's real clients (5 tests: copied voice with consent refused without it, speed
  honoured, four lines at once batched, English on the Maya stub, transcript, scores, one-speaker diarization).
- **Never run with a real model:** the batched IndicF5 path, the Maya and Indic Transcribe model calls (written
  from the libraries' documented interfaces), the QA models, the container images (no Docker here).
- **`gpu-mode.sh`:** checked with `bash -n`; its read-only `status` ran (five shared servers up, 9041-9045 down,
  mode normal). `hq` and `normal` were not run, not even as a dry run: those commands are on the do-not-run list.
- **Licences and models, verified against their own pages** (details in `MODELS.md`):
  - The speaker-similarity model used in earlier measurements (ECAPA2) is CC-BY-NC-4.0, non-commercial. The QA
    server uses SpeechBrain ECAPA (Apache-2.0); the earlier similarity figures do not carry over to its scale.
  - Indic Transcribe: free to self-host, but a hosted service that others call needs its authors' written
    sign-off. Fine for samples; a decision before production.
  - Maya 2 Native: Apache-2.0, 7.7 GB of GPU memory by its card, its own engine (not vLLM), no speed control.
  - Gemma 4 is Apache-2.0; Google publishes 4-bit checkpoints for vLLM in 12B (10.3 GB) and 31B (23.3 GB).
  - The live Whisper on 9030 is a Hindi/Hinglish model: it cannot hear Tamil or Bengali back.
- **Read from the shared translation server (HTTP, read-only):** vLLM 0.34.0, prefix caching on, 52.8% of all
  prompt tokens since its start served from the cache.
- **v0 after this phase:** all nine checks ok. Tests: 155 pass.
- **Test:** `python -m pytest tests/test_v1_servers.py -q`; a stub by hand:
  `cd gpu_engine_v1 && V1_STUB=1 uvicorn qa_server:app --port 9045`.
- **Roll back:** nothing runs; the folder can be ignored. A server that is started later is switched off by
  emptying its address in `backend/.env`.

## Phase 7: Studio HQ (`V1_STUDIO_HQ`, `V1_FIT_115`), 23 Nov 2026

- **Changed:** `app/v1/hq/` (`text.py`: merge two hearings, clean, translate with a word limit per line, review,
  numbers as words; `voice.py`: takes, scoring, picking, flagging; `finish.py`: sidechain ducking and loudness;
  `runner.py`: the three phases, one job or several jobs phase by phase), `app/v1/queue.py` (waiting HQ jobs, in
  Redis when `REDIS_URL` is set), `app/v1/qa.py` (`heard_share`). `studio/runner.py` takes the HQ path only for a
  job created with `quality=hq` while the flag is on; `V1_FIT_115` caps the speed-up at 1.15x on both paths.
  `studio/routes.py`: `quality` and `hold` on `POST /api/jobs`, `POST /api/jobs/{id}/translations/{tid}/pick`,
  `GET .../alts/{n}` (a take's audio), `POST /api/v1/hq/batch`, HQ fields on the segments. Website: an HQ choice
  on `/studio` (shown only when the flag is on), flagged lines marked in the editor with their reason, every take
  of a line with its scores, its audio and "Use this take". 13 tests with fake providers (a line that passes is
  spoken once; own voice gets more takes until one passes; a stock voice is not asked twice for the same words; a
  line that is only too long is not re-taken but sped by the engine and then shortened; a line that never passes
  is flagged with its best take; the swap; flag off = v0 path; batch order A, A, B, B, C, C).
- **How a line is judged:** share of its words heard back (at least `V1_HQ_BACKCHECK_MIN`, 0.9), speed-up needed
  to fit its slot (at most 1.15x with `V1_FIT_115`), and speaker similarity when a scorer measures it (not a gate
  yet: `V1_HQ_SIMILARITY_MIN=0`). A line no scorer could check is spoken and reported as unchecked, not failed.
- **What it used here** (routing `studio_hq`, nothing new loaded): hosted speech-to-text plus our Whisper as the
  second hearing, our small translation model for the text steps with the hosted one for review, our voice engine
  for the copied voice, the hosted speech-to-text as the scorer (words only; no speaker similarity without the QA
  server), one speaker (no diarization).

### Measured (GPU engine, voice copied from the video with consent, Tamil + Bengali, one run each)

Twelve-line class video (50 s, made from the hard set's speech, `eval/v1/make_video.py`):

| | standard (all flags off) | HQ |
|---|---|---|
| Turnaround, nothing cached | 84 s | 222 s (voices 142 s) |
| Words heard back, mean of lines | 93.4% (Tamil 93.9, Bengali 93.0) | 92.9% (Tamil 95.8, Bengali 90.1) |
| Takes | 24 (one a line) | 54 |
| Lines flagged for a person | not checked in this path | 8 of 24 |
| Largest speed-up | 1.00x | 1.02x |

Inside the HQ job, first take against the take that was picked: Tamil 85.0% -> 95.8%, Bengali 87.7% -> 90.1%
(13 of 24 lines needed more than one take). The review step changed 6 Tamil and 2 Bengali lines; 0 and 3 lines
were over their word limit; the two hearings differed in script on every line and the merge kept the first.

Dense one-line reel (24.9 s): standard 41 s, HQ 92 s; words heard back 88.2% against 87.7%; both lines of the HQ
job flagged (88% heard back, under the 90% line); the line fitted its slot unsped in both.

What the numbers say:

- **The 96% target was not reached** (92.9% on one video, one run). HQ did not beat standard on words heard back:
  picking among takes raised a line's score by 2 to 11 points over its own first take, but the HQ translation
  step produced lines that scored lower on their first take than standard's lines did (85-88% against 93-94%),
  so the two ends cancel. The text steps ran on the small translation model here; the big one is deferred.
- **The scorer was wrong on the first run, and was fixed:** a dub says an abbreviation as separate letters and the
  speech-to-text writes it as one word, so every take of such a line scored the same low number (nine lines
  flagged, 90.9%). `heard_share` now also counts a word whose letters are there with the spaces set aside; what
  was heard is kept in the cache, so old scores are worked out again without new calls. The table above is with
  the fixed rule, applied to both paths.
- **Several flagged lines have the same score on every take** (for example 0.889 four times): that is the scorer
  or the wording, not the voice. More takes cannot fix those; a person, or a better scorer, can.
- **The 1.15x limit, duration control and shortening were not exercised by these videos** (every line fitted its
  slot); they are covered by tests only. Sidechain ducking and loudness ran (mix 1.7-3.4 s) but were not judged
  by ear. Speaker similarity: not measured (needs the QA server).
- **Not done:** more than one run a path (the second run of the same video is served from the cache), a video
  with two speakers, the big translation model, Maya 2, the batch endpoint on real jobs (tests only).

- **v0 after this phase:** all nine checks ok. Tests: 155 pass.
- **Test:** `python -m pytest tests/test_v1_hq.py -q`; a real job: `V1_STUDIO_HQ=true`, then
  `python -m eval.v1.studio <video> --out <dir> --target standard=http://127.0.0.1:8111 --target hq=http://127.0.0.1:8110:hq`.
- **Roll back:** `V1_STUDIO_HQ=false` (the choice disappears and every job is standard); `V1_FIT_115=false`.

## Phase 8: eval harness and report, 23 Nov 2026

- **Changed:** `backend/eval/v1/`: `live.py` (phase 5), `studio.py` (standard against HQ, every finished line heard
  back by the same scorer through `GET /api/v1/jobs/{id}/backcheck`), `stt.py` (key words on the hard set, clean
  and hard, per provider), `make_video.py` (a many-line Studio video from the hard set), `prefix.py`,
  `hard_set.json` (the 24 lines and their 80 key words; the audio stays in the data folder).
  `scripts/v1/eval-all.sh` runs all of it, one thing at a time. `docs/v1/EVAL_REPORT.md` holds every number.
- **Correction to the phase 7 entry:** on the first video HQ equalled standard. Over three videos HQ is ahead:
  92.5% of words heard back (91.1-93.5) against 89.2% (84.9-93.4), for about three times the time. Still under
  the 96% target.
- **Found and fixed while measuring:** one dropped request to our voice engine handed a whole job's Bengali lines
  (13) to the hosted copy of the voice, because a job keeps the voice that spoke first. The job's own voice is now
  tried twice before another one answers (test added). That job was not made again.
- **Speech-to-text on the hard set:** hosted 77 of 80 clean, 71.3 hard (71-72, three runs); our Whisper 70 and 52
  (50-55).
- **Not run against v0 itself:** a test session on port 8010 was refused (it would be a session in the product
  people use), so "v0" in the report is v1 with every flag off. v0 was checked through its health endpoints only.
- **v0 after this phase:** all nine checks ok. Tests: 159 pass, 1 skipped (Postgres store, no database here).
- **Test:** `scripts/v1/eval-all.sh <data>/eval <out>`. **Roll back:** nothing to roll back (scripts and a report).

## Phase 9: operations and demo readiness, 23 Nov 2026

- **Changed:** `scripts/v1/demo-check.sh` (READY or NOT READY: v1 backend and website, every model server the
  backend calls, the hosted services, the GPU of the machine it runs on, which GPU mode, whether anyone is live,
  which flags are on), `scripts/v1/warmup.sh` with `POST /api/v1/warmup` (one small request through each service,
  each timed; a service that is not configured is skipped, not failed), `scripts/v1/backup.sh` (store, voice
  samples, trace and configuration to a bucket; never keys; `--dry` prints only), `docs/v1/RUNBOOK.md` (start and
  stop, checks, flags, routing, the GPU's two modes, roll back to v0, backup and restore), the queue and store
  tests, links to the status and numbers pages in the footer.
- **Ran here:** `demo-check.sh` -> READY (eleven checks ok; it names the laptop's own card as "the GPU of this
  machine", which on the VM will be the model servers' card). `warmup.sh` -> warm: translation 0.8 s, hosted stock
  voice 1.9 s, three voice engines 1.4 s, our speech-to-text 1.0 s, separation 1.3 s; QA server skipped (not
  configured). `backup.sh` with no bucket set: stops, copies nothing.
- **Fixed on the way:** on Windows `python3` can be a stub that opens the Store; the scripts now use the
  backend's own Python when it is there.
- **Not done (see `NEEDS_APPROVAL.md`):** a real backup (no bucket, item 13), the restore rehearsal on another
  machine, "warm and green five minutes after a VM restart" (no VM restart was ours to do), the Postgres store
  against a database (item 5: its test is written and skipped).
- **v0 after this phase:** all nine checks ok. Tests: 159 pass, 1 skipped.
- **Test:** `scripts/v1/demo-check.sh && scripts/v1/warmup.sh`. **Roll back:** nothing to roll back.

## v1.1 WS0: never die (`V1_BREAKER`, `V1_LIVE_DEGRADE`), 24 Nov 2026

Why: on 24 Nov every GPU service was unreachable at once three times (2 min, 44 min, 3 h). Live has to step down
and come back, not die; and the status page showed the laptop's own 6 GB card as "the GPU".

**First, what those three stalls were** (read-only: Windows' event log against the stream watcher's log): all
three were this laptop in Modern Standby, whose network is off ("S0 Low Power Idle, Network Disconnected").
15:05:53-15:07:46 against standby 15:05:18-15:07:04; 16:01:05-19:01:23 against standby from 16:01:00 and sleep
until 19:00:51; 19:17:07-20:01:54 against standby 19:17:03-20:01:13. The watcher had it in its own lines: the
hosted services were among the 8 that did not answer. A sleeping PC also stops the backend, so nothing in this
workstream runs during it; the cure is three `powercfg` lines (`NEEDS_APPROVAL.md` item 17). What is built here
is for the stalls a PC that is awake does have (a dead tunnel, a stuck ssh, a server down on the GPU machine).

- **Flags, and the choice:** the breaker has its own flag, `V1_BREAKER`, and the ladder its own,
  `V1_LIVE_DEGRADE`; both default off. The breaker was not put inside `V1_ROUTER`: it is attached where a GPU
  provider object is built, in the router and in v0's fixed table alike, so it works with the router on or off.
  With both flags off no breaker object exists, no provider carries one, the pipeline has no ladder, and the
  code paths are the old ones (three tests say so: providers, status answer, a Live session with a dead voice).
- **Changed, breaker** (`backend/app/v1/breaker.py`, new): one breaker per GPU endpoint (provider + host:port).
  A timeout, or 2 failures within 10 s, opens it for 30 s: calls fail at once with `CircuitOpen` and the fallback
  that was always there answers (hosted translation, hosted speech-to-text, a hosted voice). Then one try. An
  answer with a client error (HTTP 4xx) does not count against the endpoint. Hooks, each a no-op without a breaker:
  `providers/llm_openai.py` (`_chat`: a live call gets 3 s as a whole on our model), `providers/tts_gpu.py`
  (one breaker per engine: a dead engine is left out and the others keep speaking; 4 s a line),
  `providers/stt_gpu.py` (file calls, the stream's connect, and a ping every 5 s so a dead link is noticed in
  seconds). `providers/__init__.py` and `v1/router.py` attach them. Hosted providers get none.
- **Link-stall detector** (`LinkWatch`, same file): while a Live session runs, every GPU endpoint's health is
  asked every 5 s (2 s limit). All of them failing in one round is the link: every circuit opens at once, so no
  phrase pays a timeout to find out. Its probe is also the half-open try (no phrase is spent on testing a dead
  endpoint), and after a failed probe it tries again next round, so an endpoint is back in use within seconds of
  the link returning.
- **Ladder** (`backend/app/v1/degrade.py`, new; `live/pipeline.py`): copied voice, stock voice, captions only,
  original sound. Two failures in a row step down, one success steps up; while no voice answers a line still
  tries one every 10 s. New with the flag on: a line whose hosted copy of the voice fails is said in a stock
  voice; a streamer's stored voice may hold a session's start up 8 s at most and is asked for again every 15 s
  until the engines take it; any error from a voice (not only the two kinds caught before) is a failed line, not
  a crashed one. The rung goes out in the `clock` message once a second (a viewer who joins later knows it), in a
  `degrade` message on every change, in the session's metrics (`rung`, `rung_why`, `rung_changes`), in the trace,
  and per stored phrase (`rung:<lang>`: 0 copied, 1 stock, 2 no voice, 3 not translated).
  Voice stickiness is as before: a session's copied voice stays its voice; while its engine's circuit is open
  the line is said by a stock voice at once instead of waiting.
- **Viewer page** (`web/app/watch/[id]/page.tsx`, additive): a small note under the captions, "Audio returning
  shortly. Captions continue." on the captions rung and "Dub paused. You hear the original sound; the dub returns
  by itself." on the last one, where a viewer who is listening gets the stream's own sound at full volume until the
  dub is back. Nothing shows when the backend sends no rung.
- **Status page** (`v1/health.py`, `web/app/health/page.tsx`): `gpu` is now the GPU machine's own report or
  nothing; the page says "A100 (VM): unknown" until a server on the VM reports it. The card of the machine the
  backend runs on is given as `local_card` and is not shown as the GPU. `gpu_engine_v1/qa_server.py` has
  `GET /gpu` (`nvidia-smi` there: memory, use, temperature, power, per process); `V1_GPU_STATS_URL` points the
  backend at it (item 18). The page also lists the circuit breakers when the flag is on; `GET /api/v1/circuits`.
- **Stream watcher** (`scripts/v1/stream-watch.py`): `CIRCUIT OPEN <endpoint>: <why>`, `CIRCUIT CLOSED <endpoint>
  after <n> s`, `CIRCUIT LINK STALL`, `CIRCUIT LINK BACK` (asked every 20 s) and `RUNG [session] a -> b (why)`.
  A backend without the endpoint (the one running now, until it is restarted) is asked once and then left.
  **The watcher window has to be restarted to print the new lines.**
- **Tunnel watchdog** (`scripts/v1/tunnel-watchdog.ps1`, new, NOT run; item 16): tells apart no ssh, a stuck ssh,
  a dead server on the GPU machine and a PC that slept. v0's `tunnel.ps1` already reconnects by itself, so the
  watchdog starts a tunnel only when no `tunnel.ps1` window runs, and ends an ssh it did not start only with
  `-RestartStuck`.
- **Also:** `scripts/v1/ab-server.*` force the two new flags (and `V1_API_LOG`) off like the others;
  `demo-check.sh` prints the VM's card or "unknown" and any open circuit; tests force `V1_LLM_PREFIX_CACHE` off too.

### Measured

Material: the dense 24.9 s Hindi reel, six loops (about 160 s), Tamil, GPU engine, voice learned from the stream
with consent, sync mode, comparison backends on 8111-8113 with `V1_ROUTER=true`. The GPU endpoints were reached
through a small relay on the laptop that can stop passing bytes (connections stay open and get nothing: a stalled
link). One voice engine (9001), translation (9020) and speech-to-text (9030) went through it. One session at a
time; nobody was live on v0 or v1. Windows are by when a phrase was spoken.

**All three GPU endpoints stalled for 50 s, from second 43 of the session:**

| during the stall | flags off (1 run) | breaker + ladder on (3 runs) |
|---|---|---|
| phrases spoken by the speaker | 22 | 23, 24, 23 |
| translated | 4 (18 went out in the source language) | 23, 24, 23 (all) |
| dubbed | 4 | 23, 24, 23 (all, in a stock voice) |
| first audio after the phrase, median | 8.2 s (of the 4) | 3.5, 3.1, 3.4 s (before the stall: 2.1, 2.2, 2.5 s) |
| first audio, worst | 8.7 s | 7.0, 7.0, 7.7 s (the phrases caught when the stall began) |
| translated by the hosted model instead of ours | 0 | 23, 24, 23 |

With the flags off a phrase waited for our translation model until the pipeline's own 8 s limit cut the whole
call, so the hosted model was never reached. With them on the rung went to "stock" 3.1, 4.6 and 4.8 s after the
stall began, and every later phrase went straight to the hosted services. After the link returned: in the first
two runs (an earlier build, where a failed retry meant another full 30 s) the copied voice was back 34.1 and
34.5 s later, with 14 of 33 phrases still in a stock voice; in the final build (the detector probes again every
5 s) 5.6 s later, 33 of 33 phrases in the copied voice and no translation by the hosted model. One run of the
final build.

**GPU endpoints dead from the first second** (flags on, 1 run, the earlier build): 75 of 75 phrases translated and
dubbed (stock voice, hosted translation), first audio median 3.7 s / p95 5.8 s, the session ended only when it
was stopped.

**No hosted voice and no hosted translation reachable, then the voice engine stalled at 38 s, then everything at
78 s, all back at 113 s** (flags on, 1 run of the final build; an earlier run of the same plan found a bug, below):
the session went stock, captions (no hosted voice, own voice not learned yet), copied at 13.8 s, captions 4.0 s
after the voice stalled, original 19.6 s after everything stalled (the speech-to-text stream), captions, copied
8.5 s after everything returned. 67 phrases, a caption for each (1 in the source language), 21 phrases during the
stalls with no audio (15 of them not sent to any voice), 23 of 24 dubbed phrases after it in the copied voice.
The session was live throughout and ended when stopped.

**Limits against healthy calls:** over the four runs with a working GPU, through the relay: 169 voice lines, the
slowest 1.36 s (limit 4 s); 204 translation calls on our model, the slowest 1.13 s (limit 3 s). No healthy call
came near its limit. The two limits were chosen, not tuned: on 21 Nov a real stream had lines of 5-17 s on a
stalling link, and those would now go to the hosted services after 3-4 s.

**Found by the last run and fixed:** a hosted voice whose connection drops raises an error that is neither of the
two kinds the pipeline caught, so the line failed without the ladder hearing of it (the session stayed on
"stock" with no audio). With the ladder on every voice error now counts; with it off the old path is untouched.

**Not measured:** a real stalled tunnel (the relay stands in for it; the tunnel was not ours to touch); a stall
longer than 50 s; two or three languages at once; Streamer Mode with a stored voice through a stall (tests with a
fake engine only); the viewer page in a browser (type check only: the build that serves port 3100 was not
remade); the watchdog as a whole; `/gpu` on the real card. Each stall run is one or three runs on one reel: the
on/off difference is all-or-nothing, the timing numbers carry the usual run-to-run spread.

- **Tests:** 185 pass, 1 skipped (was 163 + 1). New: `tests/test_v1_breaker.py` (21: the breaker's states; a GPU
  translation model that hangs costs one short wait, then none; a dead voice engine is left out and the other
  speaks; speech-to-text with an open circuit goes straight to the hosted one; a link stall opens every circuit
  and the detector's probe closes them; the ladder down and up through all four rungs on a Live session with
  fake providers; a GPU machine that does not answer cannot hold a streamer's session start; flags off = no
  breaker anywhere and nothing about rungs sent or stored; the status answer never gives this machine's card as
  the GPU; the stream watcher's new lines, also against a backend without the endpoint) and one in `tests/test_v1_servers.py` (`/gpu`).
- **v0 after this workstream:** all nine checks ok (`scripts/v1/v0-check.sh`). Nothing of v0 was edited, started or stopped.
- **Test by hand:** `scripts\v1\ab-server.ps1 -Port 8111 -Name try -Flags "V1_ROUTER=true,V1_BREAKER=true,V1_LIVE_DEGRADE=true"`,
  a Live session on it with the GPU engine, then close the tunnel window for a minute: `/health` on that backend
  shows the circuits open, the session keeps dubbing in a stock voice, `GET /api/live/sessions/<id>/metrics`
  shows `rung`, and the copied voice returns a few seconds after the tunnel does.
- **Roll back:** `V1_BREAKER=false` and `V1_LIVE_DEGRADE=false` (the default) and restart the backend. The status
  page's GPU line and the watcher's new lines are not behind a flag: they only stop showing something wrong, or
  print more.

## v1.1 WS1: Live on dense speech (`V1_LIVE_BUDGET`, `V1_LIVE_RATECTRL`, `V1_LIVE_NATIVE_SPEED`), 24 Nov 2026

The full account with every table is `docs/v1/LIVE_DENSE_REPORT.md`. Three flags, all off by default; with them
off the Live pipeline is v0's (test `test_flags_off_nothing_new_is_asked_stored_or_built`).

### What changed

- **`backend/app/v1/dense.py`** (new, no I/O): `letters()`; `ExpansionModel` (per language and kind of voice: ms
  of dub per target letter, per target word, per source word; a running average over the lines spoken, started
  from a seed file; turns a slot into words and letters, a text into an expected duration); `RateController`
  (PI on the backlog in seconds, scale 1.0 to 0.6, lets go within seconds once the backlog is gone);
  `SpeakingShare` (share of the last 30 s the speaker talked; dense over 70%, until under 60%).
- **New per phrase and language** (`live/pipeline.py`, written with `V1_TRACE` or one of the flags; nothing with
  everything off): `dur_ratio` = dubbed seconds sent / seconds of the source slot, `backlog` (how far the dub
  queue was behind the video when the phrase's turn came), `dub_ms`, `dub_raw_ms`, `slot_ms`, `tgt_words`,
  `tgt_chars`, and with the flags `budget`, `budget_chars`, `budget_ms`, `est0_ms`, `est_ms`, `reasked`, `ctl`
  (the scale), `ctl_i` (the integral), `dense`, `share`, `native`. They are in the stored phrase, the trace
  (`v1/trace.py`, two new Prometheus histograms), `/api/v1/metrics/summary` and `/metrics-ui` (dub length / slot
  p50 / p90 and backlog p95 per language; `v1/metrics.py`, `web/app/metrics-ui/page.tsx`), a session's
  `/metrics` (`dense`, `ratectrl`, `expansion`), the stream watcher's end-of-stream summary
  (`scripts/v1/stream-watch.py`; **the watcher window has to be restarted to print it**) and `logs/sessions/`
  (`scripts/v1/collect-logs.py`, only where measured; `--more-trace` copies a comparison backend's trace).
- **`V1_LIVE_BUDGET`**: the translator gets the phrase's own slot as words and letters, a compact register and
  "keep names and numbers" (`providers/llm_local.py`, `llm_openai.py`: new `max_chars`, `compact`, sent only with
  the flag). The answer's expected duration is checked; over by more than 15%: one request for a shorter line
  (`shorten`, 2.5 s at most), used when shorter and well formed. A line that arrives late gets the time left
  until the next phrase is due. Our engine's slow speed for lines of one to three words is counted. It replaces
  v0's word limit (`live_length_budget`) for the phrases it can plan and leaves it for the rest (how the two
  relate: report, section 2).
- **`V1_LIVE_RATECTRL`**: the controller's scale multiplies that budget. Dense mode: budget at most 0.9 of the
  slot, lines under 3 words join the next (the merger of `V1_PHRASE_DYNAMIC`, active only while dense), speed-up
  up to 1.4x (`V1_DENSE_MAX_TEMPO`). Without `V1_LIVE_BUDGET` it changes only the speed limit and the join.
- **`V1_LIVE_NATIVE_SPEED`**: v0's engines take `speed` per line and no duration (`DISCOVERY.md`), so the wanted
  duration becomes a speed: at most 1.2x, never under 320 ms a word, the rest by tempo. Nothing on the engines
  was changed; the v1 voice server (:9041) was not touched.
- **Seed** `backend/config/live_expansion.json`, built by `backend/eval/v1/expansion_seed.py`. The stored history
  had no dub length: `audio_ms` in `logs/sessions/` is the time between audio messages (about 0 for a line sent
  in one piece). It can be worked out for a phrase whose successor queued straight behind it, which gives ms per
  source word only (Punjabi 266, Tamil 231, Bengali 195 on our engine's copied voice). Ms per letter and word
  come from the new fields: Punjabi 57.8 / 229, Tamil 56.1 / 360, from one flags-off run of this work. Other
  languages start on v0's limit until their first line.
- **Harness** `backend/eval/live_replay.py` (a file's sound and clock into Live in real time, any length,
  settings in turn, waits while a stream is live on 8010 or 8110, mean and spread, optional WAV per phrase) and
  `backend/eval/live_judge.py` (words heard back on a sample of those lines).
- **Also:** `ab-server.*` and the tests force the three flags off like the others; `RUNBOOK.md` has the flags
  and their settings; `logs/README.md` the new fields; `NEEDS_APPROVAL.md` item 19 asks for two or three dense
  recordings of about 10 minutes (no long real recording exists here).

### Measured

One 24.9 s reel played 8 times in a row (211 s a run; the speaker talks 89% of the time, 5.1 words a second: a
loop of one reel, no long real recording exists), GPU engine, Punjabi + Tamil, voice learned from the stream with
consent, sync mode, hold fixed at 6 s, four comparison backends in turn, **5 runs each**, mean (lowest-highest):

| | off | budget | budget + controller | + engine speed |
|---|---|---|---|---|
| Within 0.25 s of its moment | 63.5% (57.9-68.6) | 80.6% (77.8-83.6) | 83.1% (81.9-84.4) | 82.8% (80.5-85.9) |
| Within 1 s (target 90%) | 86.5% (84.2-90.6) | 92.3% (89.8-96.1) | 91.8% (89.2-95.3) | 91.5% (87.7-94.7) |
| dur_ratio p50 / p90 (target p90 1.0) | 0.98 / 1.42 | 0.91 / 1.17 | 0.85 / 1.11 | 0.84 / 1.09 |
| Backlog p95 (ms) | 1535 (1063-2043) | 844 (414-1307) | 1191 (443-2667) | 1690 (421-4588) |
| Skipped as too late per 10 min (target 1) | 7.1 (0-17.9) | 7.8 (0-35.8) | 9.5 (0-32.7) | 19.7 (0-44.8) |
| Lines at 1.3x / 1.4x, of about 185 | 46 / 0 | 24 / 0 | 8 / 15 | 9 / 16 |
| First audio p50 / p95 (ms) | 2408 / 3924 | 2627 / 4403 | 2651 / 4686 | 2618 / 4746 |
| Copied voice | 97.4% | 96.1% | 94.8% | 95.6% |

- **Targets:** within 1 s at 90%: reached with the budget (7 of 10 runs at 90% or more, the rest 89.2-89.8%).
  dur_ratio p90 at 1.0: **not reached** (1.11; Punjabi 1.05, Tamil 1.17). One skip in 10 minutes: **not
  reached in any setting**; skips come in bursts behind stalls (none in 11 of 20 runs).
- **What is left:** phrases more than 1 s late because they queued behind a long dub fell from 8.9% to 2-3%;
  those whose own audio arrived late stayed at 5-6% and are now the larger part (long utterances the recogniser
  gives out only at their end; stalls). Of the lines still longer than their slot, 65 of 108 in Tamil are lines
  of one to three words, which the engine has to say slowly.
- **Cost:** 15-18% fewer letters said (3.55 -> 2.91 a source word in Punjabi, 3.72 -> 3.08 in Tamil); every
  second line is asked for twice (translation p50 537 -> 714 ms). Words heard back, 40 lines a cell: Punjabi
  87.7% -> 80.1%, Tamil 84.4% -> 82.9%. 20 lines read against their sources: Punjabi 2 lost something that
  mattered, Tamil 7 (read by the author, not a native speaker).
- **A check with no tolerance** (`V1_BUDGET_OVER=1.0`, 3 runs against 3): dur_ratio p90 1.10 against 1.07, the
  median 0.78 against 0.84: no gain, shorter lines. Default stays 1.15.
- **Engine speed:** 6.6 lines a run, all Tamil (Punjabi is already under the pace floor); no timing number moved;
  words heard back 89.3% (33 lines) against 87.9% (33 lines sped up by tempo alone).
- **Found on the way, not fixed:** speech fed in a session's first seconds, before the speech-to-text connection
  is open, reaches it in one burst and is stamped as 27 words in a 1 s slot; the harness starts with 6 s of
  silence for that reason. In one run a session's first line took 16.8 s to its first audio.
- **Not measured:** a real long recording, one viewer language, Streamer Mode with a stored voice, a stock voice,
  the hosted engine, other languages, dense mode's parts one by one, how 1.4x sounds, the flags together with
  WS0's or with `V1_PHRASE_DYNAMIC`, the viewer's page in a browser.
- **Recommendation:** `V1_LIVE_BUDGET` on for Punjabi and languages like it; for Tamil it trades content for
  timing and is the user's call. `V1_LIVE_RATECTRL` off until someone has heard 1.4x (or with
  `V1_DENSE_MAX_TEMPO=1.3`, not measured). `V1_LIVE_NATIVE_SPEED` off.

- **Tests:** 207 pass, 1 skipped (was 185 + 1). New: `tests/test_v1_dense.py` (22: the model learns from lines, leaves out short and swallowed ones and starts a language without a seed; a missing or broken seed file; the controller tightens, never goes under its floor, does not wind up and lets go; the speaking share and its two thresholds; flags off = nothing new asked, stored or built; the budget as words and letters, the second answer used, kept out when it is in Latin letters or too slow; the fall back to v0's limit; dur_ratio and backlog stored, in the trace and in the summary; the controller's state in the metrics; dense mode joins a short line and allows 1.4x; engine speed with its floor and cap; a late line gets the time that is left and a short line counts as slow; both translators' prompts; the seed builder; the watcher's summary; the log collector; the three flags default off).
- **v0 after this workstream:** all nine checks ok (`scripts/v1/v0-check.sh`). Nothing of v0 was edited, started or stopped; its store file was read by the log collector only. No comparison backend is left running.
- **Test by hand:** `scripts\v1\ab-server.ps1 -Port 8112 -Name try -Flags "V1_LIVE_BUDGET=true,V1_LIVE_RATECTRL=true"`,
  then `python -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\ws1\try --target on=http://127.0.0.1:8112 --runs 1 --loops 4`
  from `backend\`: the table has `dur_ratio`, `backlog`, `asked to shorten`, `dense phrases`;
  `GET /api/live/sessions/<id>/metrics` shows `ratectrl` and `expansion`; `/metrics-ui` on that port shows the two
  new columns. With the flags off the same run has `dur_ratio` and `backlog` (the trace is on) and no budget.
- **Roll back:** the three flags to `false` (the default) and restart the backend. The new numbers in the trace
  and the pages are measurements only and stay.
## v1.1 WS2: session start and the English voice (`V1_LIVE_WARMSTART`, `V1_EN_SINGLE_VOICE`), 25 Nov 2026

Two flags, both off by default; with them off the Live pipeline is as it was (tests
`test_flags_off_the_start_and_the_voices_are_v0s`, `test_flags_off_english_in_a_gpu_session_is_still_chosen_line_by_line`,
`test_without_the_english_flag_a_refused_line_is_left_out_as_in_v0`).

### What v0 already did at a session's start, and what is new

v0 (`live_warmup`, on): one tiny translation for the **first** target language; one tiny hosted line for that
language, but **not** when our voice engine is going to speak it (so nothing on the voice side in a GPU session).
A streamer's stored voice was already sent to our engines when the session **started** (the first sound arriving),
and the start waited for it. In sync mode a line already waited for a copied voice that was on its way.

New with `V1_LIVE_WARMSTART` (`backend/app/v1/warm.py`, `backend/app/live/pipeline.py`):

- **Warm-up for every language and engine** (`_warmstart`, in place of `_warmup`): one tiny translation per target
  language; every process of our voice engine is asked for its state (opens its connection); when a streamer's
  stored voice is on the engines, one two-word line per language and at least one per process; one tiny hosted
  line per language the hosted voice opens in, the languages our engine takes over later included. A tiny line on
  our engine needs the session's voice: with a voice learned from the stream there is none at the start, and a
  line right after the voice arrives would stand in the way of the first real lines, so none is made then (the
  upload of the sample has just used every engine's connection). What each call took is in the session's
  `/metrics` (`warm.calls_ms`) and in the trace (`live_warmstart`).
- **A streamer's stored voice is sent when the session is created** (`prefetch_stored_voice`, called by
  `POST /api/live/sessions`), not when the sound starts; the start finds it there (`warm.calls_ms.stored_voice_ahead`)
  and, if the prefetch failed, sends it as before. The consent check is unchanged (no consent on record: nothing
  is sent).
- **A stock voice matched to the speaker** (`PitchTracker`, `pick_stock`): the session's own sound is listened to
  for pitch (autocorrelation on 64 ms windows, loud and periodic ones only; the median over at least 12 windows,
  about 0.8 s of voiced speech; 0.5 ms of CPU a window, and it stops after 160). Under 165 Hz: the language's
  male stock voice, else the female one. The voice is chosen at a language's first stock line and kept for the
  session, whatever is heard later. **Tamil and Telugu have female stock voices only**: a male speaker gets the
  female one there, and the session's `/metrics` says so (`warm.stock_voice.<lang>.note`). A matched voice that
  makes nothing gives way to the language's usual one. It applies to every stock line of the session, so also to
  a session that never gets a copied voice.
- **Opening lines do not wait for a voice that is not on its way.** v0 held a line back until 2.2 s before it was
  due whenever a copied voice was planned. Now it waits only while a sample is being sent to the engines.
- **A softened change of voice** (`_soften`): lines are separate utterances, so nothing overlaps and this is not
  a crossfade in the strict sense. Every stock line spoken while the copied voice is awaited ends in a 150 ms
  equal-power fade (any of them may be the last), the first copied line begins with one, and the first two
  copied lines are brought two thirds and one third of the way (in dB, at most 6 dB) to the level the stock voice
  spoke at. Marks per phrase: `open:<lang>`, `handover:<lang>`. **Not judged by ear.**

New with `V1_EN_SINGLE_VOICE` (GPU-engine sessions with English among the targets; nothing elsewhere):

- English is spoken in **one voice for the whole session**, decided at the start and never per line
  (`V1_EN_VOICE`): `stock` = the one stock voice for every line, also when the session has a copy; `copy` = the
  hosted copy for every line once the session has it, whatever time is spare, wherever English stands in the
  language list; `auto` (default) = the measured choice, which is `stock` (below). The session's `/metrics` says
  which (`en_voice`). With `V1_LIVE_WARMSTART` the stock voice is the one matched to the speaker (Pranav or Kaveri).
- `copy` on a voice that is still being learned from the stream cannot be one voice for the whole session: the
  lines before the copy exists are said in the stock voice (a line waits for a copy that is being made until
  3.5 s before it is due, `V1_EN_COPY_LEAD_MS`), then the voice changes once and stays.
- **A refused line is asked once more in the same voice.** The streamed hosted call has no retry of its own (the
  plain one has); a line the service refuses is silently left out. With the flag an English line refused before
  any sound is asked again after 0.2 s (`tts_retry:<lang>` per phrase, `en_lines_asked_again` /
  `en_lines_then_spoken` in `/metrics`).
- **With the ladder (`V1_LIVE_DEGRADE`):** the one voice is the session's choice while the service answers; the
  ladder still steps down when it does not. In `copy`, a line the copy refuses twice is said by the stock voice
  (the ladder's rule, rung "stock"); after two such lines in a row the copy counts as down and English is asked
  of the stock voice directly, with one try of the copy every 10 s; the first that answers brings the copy back.
  In `stock` there is nothing to step down to but captions. Without the ladder a line refused twice has no audio.
  The ladder's change is announced to viewers; it is a step for an outage, not a choice per line.
- **Harness:** `eval/live_replay.py` now also keeps the pipeline's error messages (they go to the console's feed
  only); `eval/live_first.py` (new) reads a replay folder and the comparison backends' stores: the first N
  phrases of each session, and which voice said every line of a language.

### Measured: the first 10 phrases of a session (`V1_LIVE_WARMSTART`)

The dense 24.9 s reel played twice after 6 s of silence (about 26 phrases a session; the first 10 are counted, each
in two languages = 20 lines a run), GPU engine, Punjabi + Tamil, voice learned from the stream with consent, sync
mode, hold fixed at 6 s, two comparison backends in turn (off, on, off, on ...), **5 runs each way per build**,
night of 24-25 Nov 2026. First audio = end of the phrase's speech to its first dubbed audio. Mean
(lowest-highest) over the runs; numbers from `eval/live_first.py` on `data-v1/eval/ws2/warm` and `warm2`.

| First 10 phrases | off | first build | off (second batch) | final build |
|---|---|---|---|---|
| First audio p95 (ms) | 3859 (3556-4179) | 4793 (3851-5546) | 4268 (3673-5051) | 3798 (3396-4338) |
| First audio p50 (ms) | 2887 (2721-3080) | 2892 (2563-3105) | 2904 (2721-3108) | 2856 (2621-3368) |
| Slowest line (ms) | 4507 (3929-5230) | 5170 (4187-5788) | 4627 (4181-5515) | 4285 (3552-5119) |
| Lines in a stock voice, of 20 | 5.6 (4-7) | 5.6 (5-7) | 4.6 (4-5) | 4.0 (1-7) |
| Lines in the copied voice, of 20 | 13.8 (13-14) | 14.4 (13-15) | 14.2 (14-15) | 13.6 (11-15) |
| Lines with no audio, of 20 | 0.6 (0-2) | 0 (0-0) | 1.2 (0-2) | 2.4 (0-5) |
| Lines starting within 1 s of their moment, of 20 (a line said together with the one before has no moment of its own) | 16.8 (16-18) | 14.2 (9-18) | 16.2 (14-18) | 14.6 (11-17) |

- **First build** (warm-up calls, matched voice, softened change; lines still waited for the copied voice as in
  v0): first audio p95 **worse**, 3.86 s -> 4.79 s, in 4 of 5 pairs. No cause was found in the code path (the
  pitch estimate costs 0.5 ms a window; the warm-up calls are over 5 s before the first word). By step, phrases
  1-3: stock lines took 1.93 s (off) against 2.22 s from translation to first audio, and 4 lines got the copied
  voice after waiting 3.6 s for it (off: none); phrases 4-10 were equal (0.96 s against 0.97 s for a copied line).
- **Final build** (the same, and a line no longer waits for a voice that is not on its way): p95 4.27 s -> 3.80 s,
  lower in 4 of 5 pairs, ranges overlap. **Not a proven gain:** "off" alone moved by 0.41 s between the two
  batches (3.86 s and 4.27 s), which is the size of the difference. The median did not move in either build.
- **Why there is so little to win:** on this setup nothing was cold. The hosted voice's warm-up line took 297-1428 ms
  (19 of 20 calls answered, mean 0.59 s) and the first real stock line of an "off" session, which had no warm-up,
  took 0.77-1.13 s for Punjabi; a tiny translation took 432-1104 ms and the first real one was no faster after it;
  asking the three engine processes for their state took 1.06-1.65 s. What the opening's first audio consists of is
  speech-to-text (0.85-0.93 s), translation (0.69-0.74 s), and for the stock lines the wait for the hosted
  account's one request at a time, which two languages share (1.7-2.2 s from translation to first audio).
- **Stock or copied in the first 10 phrases:** 4-6 of 20 lines in a stock voice and 14 in the copied voice, with
  or without the flag; the first line in the copied voice arrived 8.5-11.5 s after the first word, at phrase 4 or
  5, in all twenty runs. The softened change acted on 4 lines a run (two per language) in 9 of 10 runs.
- **The speaker** of the reel was measured at 222 Hz in all ten runs (213-215 Hz when the first stock line was
  chosen, about 4 s into the speech): female, so Punjabi got Mehuli and Tamil Asmita, the voices v0 uses anyway. **A male
  speaker was not measured in a session.** The eight male stock voices were each asked for one two-word line on
  the hosted service: all eight answered (0.37-0.60 s), so the names exist.
- **Lines with no audio** are stock lines of the opening that the hosted voice was asked for and did not make;
  they carry no skip mark. In these runs the reason was not recorded (the harness did not yet keep the pipeline's
  error messages); an hour later the hosted voice was refusing lines with "technical difficulties" (below), which is
  the likely reason. They are in both columns and not a product of the flag as far as these runs show (the first
  build had none, the final build the most).
- **Not measured:** Streamer Mode with a stored voice (the prefetch and the engine lines: tests with a fake engine
  only; no streamer profile exists in a comparison backend's store, and the user's recorded voice was not used
  for a test nobody asked for); a session without the 6 s of silence the harness starts with (a real console
  sends sound at once; the warm-up then overlaps the first words); a male speaker; music or game sound under the
  voice (the pitch estimate was only ever given this one clean voice); how the softened change sounds; one viewer
  language; the hosted engine.

### Measured: which voice says the English lines (`V1_EN_SINGLE_VOICE`)

The same reel played 8 times (211 s a session, about 95 phrases), GPU engine, **English + Punjabi** (English
first, as on the user's stream), voice learned from the stream with consent, sync mode, hold fixed at 6 s. Three
comparison backends in turn: flag off, flag on with `V1_EN_VOICE=copy`, flag on with `V1_EN_VOICE=stock`;
**3 runs each**, 25 Nov 2026, about 00:40 to 01:15 IST. Mean (lowest-highest); from `eval/live_first.py` on
`data-v1/eval/ws2/en2`.

**The hosted stock voice was failing that night.** It answered many lines with HTTP 502 "We are facing technical
difficulties" within 0.2 s: 5 of 18 single lines asked outside any session between 00:36 and 01:14, and in the
sessions 59% of the English stock lines at the first try. The hosted copy of the voice answered every line. On
the user's stream of 24 Nov (read from v0's store: 100 English lines, 91 copied, 9 stock, 16 changes of voice)
no line was refused by either. So the lost lines below belong to that night; the mix and the timing do not.

| English lines | off | on, `copy` | on, `stock` (= `auto`) |
|---|---|---|---|
| Spoken, of about 95 | 69.7 (65-76) | 74.3 (73-76) | 54.7 (53-57) |
| In the copied voice / in a stock voice (% of spoken) | 59.7 / 40.3 | 67.3 / 32.7 | 0 / 100 |
| Stock lines before the copy existed | 23.7 (19-31) | 24.3 (18-29) | all |
| **Stock lines between copied ones** | **4.7 (3-6), 10.1% (6.5-12.8) of the lines from the first copied one on** | **0** | **0** |
| **Changes of voice in a session** | **9 (7-11)** | **1** (opening to copy) | **0** |
| Asked for and not made (the hosted voice refused) | 25.3 (21-30) | 20 (18-21), all before the copy existed | 39.3 (39-40) |
| Asked a second time (the flag's one retry) | none | 31.3 (27-35) | 55.3 (52-58) |
| Skipped as too late | 0 | 0 | 0 |
| Within 1 s of its moment (%) | 90.9 (88.0-92.6) | 82.4 (79.5-88.0) | 90.6 (84.6-94.3) |
| First audio p50 / p95 (ms) | 2923 / 4184 | 2948 / 4298 | 2388 / 4100 |

From 120 s into the session on (the copy existed in every run; about 40 English lines a run):

| | off | on, `copy` | on, `stock` |
|---|---|---|---|
| In the copied voice / stock (% of spoken) | 90.3 / 9.7 | 100 / 0 | 0 / 100 |
| Refused, of about 40 | 3 (1-6) | **0 of 119 lines in three runs** | 17.3 (15-22) after both tries |
| Within 1 s of its moment (%) | 86.6 (76.9-92.1) | 73.7 (71.1-77.5) | 87.2 (77.3-96.2) |
| First audio p50 / p95 (ms) | 3191 / 4410 | 3085 / 4731 | 2353 / 3552 |

Punjabi in the same sessions (our engine's copied voice) was within 1 s for 92.8%, 91.4% and 89.9% of its lines:
the English voice does not reach it.

- **The mix, before and after.** Off: once the copy existed, one English line in ten was still in a stock voice,
  9 changes of voice a session (the user's own stream: 9 of 100 and 16 changes). On: none, whichever voice.
- **Every line in the copy costs timing.** A copied line's first audio comes 0.73 s later than a stock line's
  (3.09 s against 2.35 s at the median, ranges apart), and v0 used the stock voice exactly for the lines that had
  no time to spare. Without that, English lines within 1 s fell from 86.6% to 73.7% in the part where the copy
  existed (lower in 2 of 3 pairs, equal in one); over the whole session the backlog p95 rose from 862 ms to
  1359 ms and the lines at the 1.3x limit from 13.7 to 18.3 a run. No line was skipped as too late in any setting.
- **"Reliable", in the numbers measured.** Answers: the hosted copy made 119 of 119 lines here and 91 of 91 on
  24 Nov. Timing: 0.73 s later to first audio than the stock voice, 13 points fewer lines within 1 s than v0's
  mix. Presence: a copy learned from the stream said its first line 84-104 s after the first word in these six
  sessions (the collector takes 12 s of speech, and on this reel, which hardly pauses, that took a minute and a
  half; the likely cause, not proven, is that it only counts sound between a speech start and the next final
  transcript). So the copy answers reliably, but it is later, and for a session's first minute and a half it is
  not there.
- **What the flag chooses.** `auto` = **the one stock voice**: the brief for this work says that when
  always-copied makes timing clearly worse the fixed stock voice is taken, and it does make it worse. `copy` stays
  a setting for whoever prefers the speaker's voice: one change of voice, after the opening. The stock column's
  own timing (87.2%) is flattered: that night it spoke only 56% of its lines, so its queue was shorter; **the
  stock voice's timing on a healthy night was not measured.**
- **On a night like this one `auto` is the wrong choice:** the stock voice left 42% of the English lines without
  audio even with the retry (the second try was refused 71% of the time), the copy none. `V1_EN_VOICE=copy` is
  the setting for such a night. The flag does not switch by itself; that is a decision (`NEEDS_APPROVAL.md` 20).
- **The retry** brought back 16 of 55 refused lines a run in `stock` (29%). When the service is healthy it does
  nothing.
- **Found on the way, not fixed (flags off, v0's behaviour):** (1) the streamed hosted voice has no retry, so every
  refused line is silently without audio (25 of 95 English lines a run that night with the flag off; the opening
  stock lines of a Punjabi + Tamil session too, 0.6-1.2 of 20). (2) The hosted copy learned from the stream arrived
  84-104 s into dense speech (`SPEC.md` has 33-37 s on other material).
- **Not measured:** a healthy night; a session that has the hosted copy from its first line (a recorded voice); a
  real stream with pauses (on 24 Nov's stream 97.9% of the English lines were within 1 s with 91% of them copied);
  the two flags together; the ladder with either setting on real services (tests with fake providers); English
  as the only viewer language; how either voice sounds.
- **Hosted calls this cost:** 32 Live sessions with hosted speech-to-text and the hosted voice for the stock and
  English lines (20 of 1 minute for the session start, 9 of 3.5 minutes for English, and 3 of up to 2.7 minutes
  in a first English attempt that was stopped when the refusals showed), 18 single stock lines to see whether the
  service answered, 8 two-word lines for the male voice names.

- **Tests:** 241 pass, 1 skipped (was 207 + 1). New: `tests/test_v1_warm.py` (34: pitch of a low and a high voice,
  none for noise or a pause; the tracker's first second and its stop; the nearest stock voice and the note for
  Tamil and Telugu; fade, level and the step towards a level; `copy` / `stock` / `auto`; both flags off by
  default; flags off = v0's warm-up, v0's voices, nothing new stored, no prefetch, English chosen line by line, a
  refused line left out; warm start asks every language and engine; engine lines with a stored voice; a failing
  warm-up call stops nothing; the matched voice is kept and the note is in the metrics; a matched voice that
  makes nothing gives way; the softened change; an opening line waits only while a sample is on its way; the
  stored voice sent at creation, not again at the start, never without consent; English always the copy, always
  the stock voice, `auto`; `copy` on a voice still to be learned; the ladder steps English down and back; a
  refused English line asked once more; the flag does nothing outside a GPU-engine session or without English;
  every language has a stock voice for either speaker).
- **v0 after this workstream:** all nine checks ok (`scripts/v1/v0-check.sh`). Nothing of v0 was edited, started or stopped; its
  store file was read (the 24 Nov stream's English lines, the log collector). No comparison backend is left running.
- **Test by hand:** `scripts\v1\ab-server.ps1 -Port 8112 -Name try -Flags "V1_LIVE_WARMSTART=true,V1_EN_SINGLE_VOICE=true,V1_EN_VOICE=copy"`,
  then from `backend\`:
  `python -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\ws2\try --target on=http://127.0.0.1:8112 --runs 1 --loops 8 --langs en-IN,pa-IN`
  and `python -m eval.live_first ..\data-v1\eval\ws2\try --data on=..\data-v1\ab\try --lang en-IN --after-s 120`.
  `GET /api/live/sessions/<id>/metrics` shows `warm` (the calls, the speaker's pitch, the stock voice per
  language and why) and `en_voice`.
- **Roll back:** `V1_LIVE_WARMSTART=false`, `V1_EN_SINGLE_VOICE=false` (the defaults) and restart the backend.

## v1.1 WS3: Studio HQ toward 96% (25 Nov 2026)

Six flags, all off by default, all acting on HQ jobs only (`V1_STUDIO_HQ`). With them off an HQ job makes the
same calls, stores the same fields and keeps the same cache keys as before (tests below).

### Found first: the judge had been taking points off Bengali for nothing

Before anything was built the takes of the 23 Nov HQ jobs were read: what the dub should say against what the
judge heard, for every kept take under 90%. The judge was already the hosted speech-to-text for every one of the
269 stored takes of the seven HQ jobs (`scored_by: prisma`); the fault was in the comparison. One Bengali letter can be stored two ways
(য়, ড়, ঢ় as one code point, or as the base letter and a dot under it). The translation model writes one form,
the speech-to-text the other; on screen they are the same letter, and v1 counted them as different words. A
Bengali line heard back word for word scored 86% ("স্নাইপার দিয়ে হেডশট মারলাম, কী দারুণ ক্লাচ!": the word
"দিয়ে" was "missed"), and every take of it scored the same, which is why Bengali lines were flagged with the
same score on all four takes. Devanagari has the same two forms (क़ ख़ ग़ ज़ ड़ ढ़ फ़); Tamil does not.

### Built

- **Judge (`V1_HQ_JUDGE`, `app/v1/hq/judge.py`, `qa.py`).**
  - Who hears a line back is a table per language: `V1_HQ_JUDGE_ORDER=prisma,whisper_gpu,qa_server`, with
    `V1_HQ_JUDGE_BY_LANG` for single languages. A judge that does not hear a language is left out for it. Our
    Whisper on :9030 is a Hindi and Hinglish model (`language="hi"` is fixed in the engine), so it is a second
    judge for Hindi lines only; it writes Latin letters, which the local model puts into Devanagari before the
    comparison, and a transcript that cannot be put into Devanagari is no judgement. The QA server's multilingual
    Whisper (:9045) is the third judge and hears every language; it has never run (`NEEDS_APPROVAL.md` items 6, 22).
    So today: Hindi has two judges, Tamil, Bengali and the rest have one, and a take nobody could hear is stored
    as "not checked", spoken, not flagged, as before.
  - The comparison brings both texts to one spelling of every letter (Unicode NFC) and drops joiners that cannot
    be seen instead of splitting a word at them (`qa.HEARD_RULE_NFC`, "nfc-2"). Nothing else about the rule moved:
    a test holds the old and the new rule to the same result on lines without such letters.
  - Recorded: every take stores `scored_by`, the rule and (new) what was heard; the line's `qa` has `by` and, when
    a judge was passed over, `passed_over`; the trace's `studio_line` has `scored_by` and `judge_passed_over`;
    `GET /api/v1/jobs/<id>/backcheck` returns `judges` (who scored how many lines) and `rule`.
  - A score stored under another rule is worked out again from what was heard, without hearing again
    (`hq/voice.py`, the eval route, the calibration page).
- **Re-scoring old jobs (`python -m eval.v1.rescore`).** Reads a backend's store and cache, never writes them.
  Takes: the hearing of that day from the score cache, counted by the rule in use. Finished lines: the file in the
  job folder, or, when the job has expired and its folder is gone (uploads are kept for 24 h), the kept take
  fitted to its slot again. `--hear` lets the judge hear what is not in the cache, `--write-hearings` puts the
  hearings where the calibration page finds them.
- **Calibration (`V1_HQ_CALIBRATE`, `app/v1/hq/calibrate.py`, four routes, `web/app/studio/calibrate/page.tsx`,
  `docs/v1/CALIBRATION.md`).** Plays a take with the words it should say and nothing else, takes good / bad /
  skip (keys g, b, s), one undo. Labels in `<DATA_DIR>/calibration/labels.jsonl`. Shows agreement at the flag line
  in use with its four counts, and a recommended flag line: the cut with the highest balanced accuracy over the
  labels. Under 30 labels, or under 5 of either kind, it recommends nothing and says how many are missing; with
  none it says "No labels yet". Labels on takes scored under another rule are counted apart, not mixed in.
- **Adaptive takes (`V1_HQ_ADAPTIVE`, `hq/voice.py`).** One take; more, up to `V1_HQ_ADAPTIVE_MAX` (5), only while
  the best score is under `V1_HQ_ADAPTIVE_MIN` (0 = the flag line), and none once two takes were heard back as
  exactly the same words when `V1_HQ_ADAPTIVE_SAME_STOP` is set (off by default, measured below). v1 already
  stopped at the first take that passed, with a limit of 4; what is new is the limit of 5 and a threshold of
  its own. `V1_HQ_TAKES_FIXED=N` makes every take regardless, to
  have something to compare with.
- **Normaliser (`V1_HQ_NORMALISE`, `hq/normalise.py`).** Rules, no model, before the voice sees the line (and
  before v1's model-written step, which then only sees what the rules left): whole numbers to 99,99,99,999 counted
  the Indian way, decimals, native digits, `dd/mm/yyyy` dates, clock times, ₹ / Rs. / INR with lakh, crore and
  thousand, $, %, ranges, km kg cm mm ml GB MB, Dr. Mr. Mrs. vs. etc., & + = @, and for our own voice (which reads
  only the language's own letters) abbreviations in capitals letter by letter. **Covered: Hindi, Bengali, Tamil,
  English. Not covered: Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi** (their lines are left to the
  model step as before; the number words of those six were not written because nobody here can check them).
  The rules know no grammar: a case ending after a figure stays as the translator wrote it.
- **Auto-glossary (`V1_HQ_AUTO_GLOSSARY`, `hq/glossary.py`).** From the job's first hearing, by rule: names (a
  capitalised word in Latin letters, runs of them, a capital inside a word), abbreviations (DNA, T20), English
  terms said in two or more lines of a transcript in another script, and, as proposals only, long words of the
  transcript's own script said in three or more lines. Used for this job's cleaning, translation and review;
  stored in the job's `meta.json`; never written to the shared glossary.
  `GET /api/v1/jobs/<id>/glossary-candidates` shows them for any job.
- **Review (`V1_HQ_REVIEW`, `hq/review.py`).** The hosted model (the `gemini` provider object of `providers/`,
  through the router's walk with its timeout; the routing file's `review` list when it is not configured) gets
  every line with the source, the first hearing where it differs, and the word limit, and the rubric: meaning
  kept; numbers and names kept; natural spoken register; fits the slot. It answers ok or the failed rule, the
  corrected line and a note. A line failed without a corrected line is asked for once more. An edit in the wrong
  script, empty, or over the word limit is refused. Every edit, taken or refused: the trace gets kind
  `hq_review_edit` (job, language, line, rule, words and letters before and after, taken, model: no text),
  `<DATA_DIR>/hq_review/<job>.jsonl` gets the same with the source, both lines and the note. A test checks that
  none of the words reach the trace.
  The flag also guards the transcript: a merged or cleaned line that is no longer the line that was heard is
  put back (`keeps_source`; what it found is the next heading).

### Found second: the HQ transcript steps change what the video says, and heard-back cannot see it

Heard-back compares the dub with its own text. It says nothing about whether that text is what the speaker said.
Reading the stores of the HQ jobs (the first hearing, kept as `src_text_raw`, against the line after v1's "merge
the hearings" and "clean" steps) showed, on 23 Nov and again in today's reruns with every v1.1 flag off:

- **Video C (`class12c`): 12 of 13 lines hold the line before them.** The merge step gives the model each line
  with the line before and after as context, and the model answered with the line before. Every dubbed line from
  the second on says what was said one line earlier; the last line of the video is never said. This job scored
  93.3% heard back today and 91.1% on 23 Nov.
- **Video B (`class12b`): all 13 lines came back in Latin letters** (the script our Whisper writes), three
  of them without their first words: "जल्दी से chat में बताओ" became "Main batao", "oxygen की कमी से ..." lost
  "oxygen", "embryo के अलग अलग stage ..." lost "embryo". 98.1% heard back today.
- Video A: no line changed in either run.

So two of the three HQ jobs behind the 23 Nov figure, and behind today's "HQ as v1 built it" figure, dub a
transcript that is not what was said. With `V1_HQ_REVIEW` a cleaned line that is no longer the line that was
heard is put back (`keeps_source`: every English term of the first hearing still there, the words of the
transcript's own script still there in that script, not more than four words in ten gone). In today's all-flags
jobs: video A 1 line changed (Pastor to Pasteur), video B 1 (a capital letter), video C 12 merged, 8 put back,
the 4 left are a capital letter, a spelling, punctuation and one added "इस"; by the same rule none of the 38
lines is "not the line heard". The guard is a rule about words, not a proof that a line is right.

### Measured

Three videos of twelve spoken lines (`class12`, `class12b`, `class12c`; 24, 26 and 26 dubbed lines a job), Tamil
+ Bengali, GPU engine, the voice copied from the video with consent, as on 23 Nov. **One job per video and
setup**, 25 Nov 2026 01:48-02:45 IST, one job at a time, no stream live on v0 or v1 before any job. Every
finished line (the audio that is in the video, after fitting) heard back by the hosted speech-to-text and counted
by the corrected rule; all 380 lines of the 15 jobs were judged by it, none by a fallback. Mean
(lowest-highest video). Raw: `data-v1/eval/ws3/run1/` (`table.md`, `table.json`), stores in `data-v1/ab/ws3-*`.

Setups (comparison backends, `scripts/v1/eval-studio-ws3.sh`): **standard** = every flag off; **HQ** = v1's HQ
(`V1_STUDIO_HQ`, `V1_FIT_115`, `V1_ROUTER`) with `V1_HQ_JUDGE`; **fixed 5** = HQ + `V1_HQ_TAKES_FIXED=5`;
**adaptive** = HQ + `V1_HQ_ADAPTIVE` (with the same-words stop on); **all flags** = adaptive + `V1_HQ_NORMALISE`
+ `V1_HQ_AUTO_GLOSSARY` + `V1_HQ_REVIEW`. Fixed 5 and adaptive were given the HQ job's transcript and translation
from its cache, so those three speak the same lines; their "total" has no transcription or translation in it.

| | Standard | HQ | Fixed 5 | Adaptive | All flags |
|---|---|---|---|---|---|
| **Words heard back** | 90.6% (88.4-93.0) | **95.9%** (93.3-98.1) | 96.1% (92.3-99.1) | 95.0% (93.2-97.8) | **94.5%** (93.2-96.5) |
| Video A / B / C | 88.4 / 90.4 / 93.0 | 96.3 / 98.1 / 93.3 | 96.8 / 99.1 / 92.3 | 94.0 / 97.8 / 93.2 | 93.2 / 93.9 / 96.5 |
| Tamil A / B / C | 82.9 / 95.5 / 90.7 | 96.6 / 97.8 / 87.5 | 96.6 / 99.0 / 87.0 | 93.1 / 99.0 / 88.7 | 90.7 / 94.3 / 96.2 |
| Bengali A / B / C | 94.0 / 85.4 / 95.2 | 95.9 / 98.4 / 99.2 | 96.9 / 99.2 / 97.6 | 94.9 / 96.5 / 97.6 | 95.7 / 93.5 / 96.8 |
| Total time A / B / C (s) | 81 / 54 / 66 | 133 / 117 / 136 | 193 / 195 / 199 | 86 / 86 / 101 | 140 / 129 / 130 |
| Voice stage A / B / C (s) | 23 / 24 / 25 | 73 / 67 / 79 | 170 / 176 / 178 | 62 / 66 / 79 | 77 / 73 / 75 |
| Takes made A / B / C | 24 / 26 / 26 | 45 / 45 / 53 | 120 / 130 / 130 | 43 / 45 / 55 | 53 / 52 / 51 |
| Lines flagged A / B / C (of 24 / 26 / 26) | not scored in the job | 5 / 3 / 7 | 3 / 1 / 7 | 6 / 4 / 8 | 8 / 9 / 4 |
| Transcript lines that are not the line heard A / B / C | does not merge | 0 / 13 / 12 | 0 / 13 / 12 | 0 / 13 / 12 | 0 / 0 / 0 |

**Target: 96% of words heard back. Not reached.** HQ: 95.9% over the three videos (two of three videos over 96%,
the third 93.3%), and two of those three dubs are of a damaged transcript. All flags, the setup whose dubs say
what the videos say: 94.5%, with one video of three over 96%.

**Before and after.** The judge did not change (hosted speech-to-text then and now); the counting rule did. The
23 Nov figures in `EVAL_REPORT.md` section 2 are by the old rule and are not comparable with today's. The 23 Nov
output was scored again by the new rule from the hearings of that day (`eval.v1.rescore`), which makes it so:

| | 23 Nov, as reported (old rule) | 23 Nov output, new rule | 25 Nov rerun, new rule |
|---|---|---|---|
| Standard, words heard back | 89.2% (84.9-93.4) | 91.1% (87.3-95.3) | 90.6% (88.4-93.0) |
| HQ, words heard back | 92.5% (91.1-93.5) | 95.5% (93.9-96.7) | 95.9% (93.3-98.1) |
| HQ Tamil A / B / C | 95.8 / 97.4 / 90.2 | 95.8 / 97.4 / 90.2 (no such letters in Tamil) | 96.6 / 97.8 / 87.5 |
| HQ Bengali A / B / C | 90.1 / 89.6 / 92.1 | 96.1 / 95.9 / 97.7 | 95.9 / 98.4 / 99.2 |
| HQ lines flagged, of 76 | 25 | 15 (the same kept takes under 90% by the new rule) | 15 |
| HQ takes made | 179 | 179 | 143 |
| HQ total time A / B / C (s) | 222 / 312 / 232 | the same jobs | 133 / 117 / 136 |
| Standard total time A / B / C (s) | 84 / 78 / 84 | the same jobs | 81 / 54 / 66 |

- What could be scored again: all 179 takes of the three 23 Nov HQ jobs (their audio is in the cache and their
  hearings in the score cache) and all 152 finished lines. The HQ jobs' folders had expired, so their 76 finished
  lines were made again from the kept take and its slot (the fit step is the same ffmpeg call); 75 of them matched
  the stored hearing by content, 1 did not and was heard again (one hosted call). The 76 standard lines were in
  their job folders. Nothing was synthesised. What could not: nothing was missing for these six jobs.
- The new rule moved Bengali by 5.6 to 6.3 points on the HQ jobs and 2.7 to 4.6 on the standard ones, and Tamil
  by nothing. Ten of the 25 flags of 23 Nov were this spelling fault.
- **So HQ did not get better between 23 and 25 Nov: it had been at 95.5% all along and was reported as 92.5%.**
  The 0.4 point between the two HQ columns is inside what one job a video shows (the same standard pipeline gave
  93.9% and 82.9% for Tamil on video A on the two days).
- HQ is about half the time it took on 23 Nov (128 s against 255 s a video). Part is fewer takes (143 against
  179: Bengali lines that used to "fail" on every take now pass on the first), part is that one 23 Nov job had
  moved to the hosted copy of the voice; how much is the hour of the night was not separated.

**Adaptive against fixed takes, same lines.**

| | Fixed 5 | Adaptive | |
|---|---|---|---|
| Voice stage, three videos (s) | 524 (170 / 176 / 178) | 206 (62 / 66 / 79) | **61% less** (64 / 62 / 56) |
| Whole job as run here (s) | 193 / 195 / 199 | 86 / 86 / 101 | 56 / 56 / 49% less |
| Takes | 380 | 143 | |
| Words heard back, finished lines | 96.1% (92.3-99.1) | 95.0% (93.2-97.8) | 1.1 points lower, in separate jobs |
| Lines flagged, of 76 | 11 | 18 | |

- The two columns are separate jobs with their own takes, and a take is a random draw: the 1.1 points are not a
  clean measure of the rule. The clean one is the rule applied to the 380 takes the fixed jobs made, in the order
  they were made (`eval.v1.studio_table`, scores of the takes before fitting): best of five 96.8%; "one take, more
  only under 90%, at most five" keeps the same take on all 76 lines (96.8%) with 145 takes instead of 380; the
  first take alone 93.8%. **Heard-back did not change, for 62% fewer takes.**
- With the same-words stop (`V1_HQ_ADAPTIVE_SAME_STOP`, as the adaptive jobs ran): 129 takes, 96.3%, a
  lower-scored take kept on 3 of 76 lines. It is off by default after this: 16 takes are not worth 3 lines.
- Against v1's own rule (up to four takes until one passes) adaptive saves nothing: both made 143 takes (voice
  stage 73 s and 69 s a video). v1 was already adaptive; what was missing was the number for fixed takes.
- Picking among takes is still where HQ's gain is: first take 93.6%, kept take 96.4% in the HQ jobs (29 of 76
  lines needed more than one take).

**The text flags (all-flags jobs).**

- **Review:** 76 lines read, 24 edits, all taken (12 numbers and names, 9 meaning, 2 register, 1 length); 4
  lines failed without a corrected line were asked for again and came back corrected. The notes include a wrong
  number ("one hour" for "one and a half hours"), a place name misspelt, a verb that changed the meaning
  ("gave the vaccine" for "made the vaccine"), subject terms that had dropped out. Two languages, hosted model,
  77 model calls in the three jobs (HQ without the flags: 42). Whether an edit was right was read from its note,
  not judged by a speaker of Tamil or Bengali.
- **A first build was measured too** (three jobs, before the "ask again" step and the stricter transcript
  guard): 94.8% (93.0-95.8), 30 edits of which 2 refused; one of the two was the wrong verb above, named by the
  reviewer and left in the dub because no corrected line came with it. That is why the step was added.
- **Auto-glossary:** 16 candidates over the three videos (Edward Jenner, Sensex, Nifty, Valorant, BGMI, RBC, DNA,
  RNA, PCR, oxygen; and "Pastor", the first hearing's spelling of Pasteur, which the cleaning step corrected).
  Not proposed: names said once in lower case by the hosted speech-to-text (hemoglobin, jet). Its effect on the
  dub was not separated from the review's.
- **Normaliser:** did nothing in these jobs (0 lines changed by rule, 0 by the model step): the test videos say
  their numbers as words ("पांच सौ point", "डेढ़ घंटे") and the translator writes them as words. **Not measured
  on real material**; tested by unit tests only (below).
- **The all-flags jobs score lower on heard-back than HQ (94.5% against 95.9%, 21 lines flagged against 15),**
  first build and final build alike on videos A and B. Read line by line, the flagged lines are mostly a
  spelling the judge writes differently for the same sound (Bengali নিচে / নীচে, হলো / হল; Tamil ஐந்நூறு / ஐநூறு,
  யாரு / யார், ஆகுறத / ஆகிறத, பிராப்ளம் / ப்ராப்ளம்) and English terms in the other script, of which the reviewed
  lines have more because the review keeps them. On video B the HQ job is also dubbing a transcript with words
  missing, which is easier to say. Whether those lines sound wrong to a person is what the calibration page is
  for; nobody has listened.

**Calibration:** no labels yet, so no agreement figure and no recommended flag line. The page was opened
against a backend holding the takes of a real job: 53 takes offered, blind, audio served, summary "no labels
yet". The takes of the 23 Nov jobs are prepared for it (189 hearings written to `data-v1/calibration/`).

**Not measured:** more than one job per video and setup (the spread between two equal jobs is large: see Tamil on
video A); speaker similarity; any language but Tamil and Bengali; **Hindi as a target** (our Whisper as second
judge was tested with fakes only, and the hosted judge writes English words in Latin letters where a Hindi dub
for our voice has them in Devanagari: its score on Hindi will be too low until that is looked at); the judge
failing in a real job (it never did: 0 lines passed over); the normaliser on a video with digits; the glossary
alone; a video with music; a long video; the same-words stop off in a real job (the default now; its numbers
above are from the fixed jobs' takes).

### Mistakes made in this work, and what they cost

- **The first fixed-5 and adaptive jobs were spoken by the hosted copy of the voice, not by our engine.** The
  script copied the HQ backend's `clone` cache to the other backends; the cached voice names a sample file in
  the first backend's voices folder, our engine could not open it, and the job fell to the hosted copy (v1's
  rule: the voice that speaks first keeps the job). Seen in the takes' `provider`, the two jobs were set aside
  (`run1_bad/`), the script no longer copies `clone`, and both setups were run again on fresh backends. Cost: 150
  lines on the hosted copy and their 150 hearings. It is also a fault waiting in the product: a cached copy of a
  voice whose sample file is gone silently moves a whole job to the hosted copy, with one line in the warnings.
- **Five comparison backends (ports 8111-8115) are still running.** They were started through Git Bash; stopping
  their task ended the wrapper and left the server. Ending a process by its id is on the list of commands not to
  run, so they were left, idle. The three started through PowerShell (8116-8118) stopped when their task was
  stopped; `eval-studio-ws3.sh` now says to start backends that way.
- Short test runs and one cache-reading script ran on the laptop while five of the jobs were running (a few
  seconds of CPU each). The jobs' time is in the voice engine and the hosted calls; no job was repeated for it.
- Hosted and GPU use of this work, all 20 jobs (15 counted, 3 from the first build of the all-flags setup, 2 set
  aside, 1 of them stopped at render): 152 clips transcribed by the hosted service (437 s of audio), 1137 takes
  and 480 finished lines heard back by it (and 1 old line for the re-scoring), 1224 voice lines (150 by the hosted copy), 187 model calls (the review's on the hosted
  model), 18 voice copies made.

- **Tests:** 275 pass, 1 skipped (was 241 + 1). New: `tests/test_v1_hq_ws3.py` (34: the six flags listed and off;
  the two spellings of a letter equal only under the new rule and nothing else moved; judge off = the routing
  list, the old rule, the old fields; judge on = first judge, who judged, who was passed over; our Whisper judges
  Hindi only and a transcript it cannot put into Devanagari is no judgement; the QA server as third judge; the
  order per language; a stored hearing scored again under the rule in use; take plans; adaptive one take, up to
  five, its own threshold, the same-words stop on and off; fixed takes; number words of Hindi, Bengali, Tamil and
  English against written-out values, every table whole and without repeats, every number up to a lakh different;
  lines with the rupee sign, %, units, dates, clock times, lakh, titles, native digits and ranges in each of the
  four; abbreviations spelled for our voice only; the six uncovered languages left alone; glossary candidates
  from a Hindi and from a Latin transcript; review edits only what fails, refuses a wrong script and an
  over-long line, logs every edit, and none of the words reach the trace; asks again for a failed line without a
  correction; an unusable answer changes nothing; the transcript guard on lines taken from real jobs; a whole HQ job
  with the text flags on; **a whole HQ job with every new flag off: the same model calls in the same order, the
  same meta fields, the same fields on a stored take, no new folder**; calibration with no labels, the blind
  queue over the score range, agreement and the recommended line on labelled takes, a stored hearing under the
  rule in use, labels under another rule left out; the calibration and glossary routes 404 without their flags).
  Website: `npx tsc --noEmit` clean.
- **v0 after this workstream:** all nine checks ok (`scripts/v1/v0-check.sh`). Nothing of v0 was edited, started or
  stopped. **Five comparison backends are left running** (8111-8115, see the mistakes above).
- **Test by hand:** v1's `backend\.env`: `V1_HQ_JUDGE=true`, `V1_HQ_ADAPTIVE=true`, `V1_HQ_REVIEW=true`,
  `V1_HQ_AUTO_GLOSSARY=true`, `V1_HQ_NORMALISE=true`, `V1_HQ_CALIBRATE=true`; restart the backend; dub a video on
  `/studio` with the HQ choice; `/studio/calibrate` for the labels; `GET /api/v1/jobs/<id>/backcheck?lang=ta-IN`
  for the judge of every line; `data-v1\hq_review\<job>.jsonl` for the review's edits. To repeat the comparison:
  the head of `scripts/v1/eval-studio-ws3.sh`, then
  `python -m eval.v1.studio_table ..\data-v1\eval\ws3\run1 --ab ..\data-v1\ab --names fixed=ws3-fixed2,adapt=ws3-adapt2,new=ws3-new2`
  (from `backend\`; `--names` because this run's second set of backends had folders of their own).
- **Roll back:** the six flags to `false` (the defaults) and restart the backend. Labels and review logs stay in
  the data folder and do nothing while the flags are off.

## v1.1 WS4: pitch kit (25 Nov 2026)

Two flags, both off by default: `V1_LIVE_RECORD` (a Live session's dub kept on disk, when that session also asks
for it) and `V1_LISTEN_TEST` (a blind A/B listening page). With them off nothing new is asked, stored or shown
(tests below). Nothing of v0 was touched.

### Built

- **A recorded session** (`backend/app/v1/record.py`, hooks in `app/live/pipeline.py`, `routes.py`, `session.py`).
  SPEC section 10 says Live audio is never stored, so this needs two yeses: the flag on the backend and
  `record: true` on `POST /api/live/sessions` for that session. The console (`/live`) shows a tick "Keep a
  recording of this session's dub on this server" only while the flag is on, never ticked by itself, with what is
  kept and that it stays until someone deletes it; a session that is being kept shows a chip saying so. With the
  flag off the ask is ignored and the answer of the route is the same as without it.
  Kept under `<DATA_DIR>/recordings/<session>/` (`V1_RECORD_DIR` to put it elsewhere): `dub_<lang>.wav`, one
  continuous mono track per language on the session's clock with every phrase where a viewer's player starts it
  (the same playhead the pipeline already keeps for its lateness numbers); `phrases.jsonl`, per phrase and
  language: seq, when it was said, the video's time at that moment, where its dub starts, its length, how late,
  the hold, first audio, copied or stock voice, tempo, the caption text, or that it was skipped and why;
  `session.json`. The stream's own sound is not kept. The caption text is in that folder only: not in the trace
  (one `live_record` event: session and number of languages), not in the store, not in `logs/`.
- **The side-by-side renderer** (`scripts/v1/render-pitch.ps1`, which calls `backend/app/v1/pitch.py`; ffmpeg does
  the picture). Left the source video with its sound, right the same video with the dub; burned in: the dub's
  captions (one at a time, in the right half), the language with "AI-dubbed live by Bharat Dub", three lines of
  numbers, and beside each caption how late that line started. Each phrase's sound is cut from the session track
  and laid at the video time it was spoken at plus its lateness: what a viewer saw and heard. Stereo:
  `split` (original left ear, dub right ear), `dub`, `mix` (dub over the original at 18%, as `/watch` plays it).
  **Every number on the picture is computed from that recording's `phrases.jsonl`**: median first audio and over
  how many phrases, share within 0.25 s and within 1 s of the video moment, phrases dubbed of phrases, how many
  in the copied voice. A recording without the video's clock (a microphone session) gets no on-time line.
  `-LeadS`, `-Loops`, `-GapMs` rebuild how the replay harness played a file in (first frame held, last frame held
  in a gap); `-OffsetMs` places a microphone session. `eval/live_replay.py` got `--record`.
- **The blind listening test** (`backend/app/v1/listen.py`, page `web/app/listen-test/page.tsx`, summary on
  `/metrics-ui`, `scripts/v1/make-listen-pairs.py`). Pairs come from `<DATA_DIR>/listen/pairs/manifest.json`
  (format in `RUNBOOK.md`): pair id, clip A, clip B, the system that made each, optional language and line. The
  page is sent, per pair, an id, the language and the line; the two sounds are fetched as "first" and "second" of
  that pair, never by file name or system, and which system is first is decided by a hash of the listener's id and
  the pair's id (different between listeners, fixed for one). The order of the pairs is also the listener's own.
  A listener rates each clip 1 to 5 and says first, second or no difference; the server turns that back into
  systems and appends it to `<DATA_DIR>/listen/results.jsonl`; a later answer of the same listener for the same
  pair replaces the earlier one. The listener's id is a random string made by the browser, no name. Summary per
  system: mean rating, number of ratings, share of the stated preferences, how often it was played first; with no
  answers it says "no ratings yet". Routes: `GET /api/v1/listen/pairs`, `/audio/<pair>/<1|2>`, `/summary`,
  `POST /api/v1/listen/answers`; all 404 with the flag off. `make-listen-pairs.py` builds the folder from two
  folders of same-named clips and copies them under numbered names, so nothing in the folder names a system.
- Also: `scripts/v1/ab-server.sh` had a broken line since WS3 (a literal backslash-n in the list of flags, which
  made the shell set a variable called `n` and nothing else wrong); fixed. Both `ab-server` scripts switch the two
  new flags off like the others.

### Measured

One recorded session, to prove the chain, not to measure Live (one run proves nothing about timing; two equal
runs differ by about 10 points). 25 Nov 2026, 03:15 local, no other stream live on 8010 or 8110, comparison
backend on 8120 started through PowerShell with `V1_LIVE_RECORD=true`, `V1_LIVE_BUDGET=true` (the flag
`SUMMARY.md` recommends for Punjabi), trace on, everything else off. The dense reel (`data-v1/eval/reel25.mp4`,
24.9 s) played 3 times with 0.4 s between and 6 s of silence first (84.8 s fed), Punjabi only, GPU engine, voice
learned from the reel.

| | This session |
|---|---|
| Phrases, and lines spoken | 36 phrases in 35 voice calls (two were spoken in one call), none skipped |
| Recording | `dub_pa-IN.wav` 88.1 s, 4.2 MB; `phrases.jsonl` 35 rows |
| First audio, median | 2.3 s (the picture: 2.275 s over the 35 lines; the trace over the 36 phrases: 2.331 s) |
| Within 0.25 s / 1 s of the video moment | 91.4% / 97.1% (the picture and the trace give the same two figures) |
| In the copied voice | 33 of 35 lines (the first two were stock, before the voice was learned) |
| Latest line | 4.1 s after its moment |
| Rendered video | `data-v1\pitch\reel25_pa-IN_split.mp4`: 82.1 s, 37,022,909 bytes (35.3 MB), 812 x 720 (two panes of 406 x 720), 30 frames a second, H.264 + stereo AAC |

- The rendered file was checked, not only made: two frames were looked at (labels, the three lines of numbers, a
  Punjabi caption in Gurmukhi with its letters joined properly, "this line +0.2 s"); the left channel is silent
  during the 6 s lead and carries the original after it, the right channel is silent until the first dubbed
  line at 7.75 s and carries the dub after it.
- How long the render took was not timed.
- **Not measured:** a recording from the console in a browser with a real YouTube video (the tick and the chip
  were type-checked, not clicked: the website on 3100 serves an older build); a microphone session through the
  renderer on real material (`-OffsetMs`, unit-tested on made-up rows); more than one language in one recording
  on real material (unit-tested with one); a long session (the track is written as it goes, 2.9 MB a minute and
  language at 24 kHz; not run for longer than 88 s); the listening test with real clips and real listeners (no
  pairs exist yet: WS5 makes them); `dub` and `mix` stereo on the real recording (unit-tested as filter text
  only; `split` is the one rendered and checked).

- **Tests:** 292 pass, 1 skipped (was 275 + 1). New: `tests/test_v1_pitch.py` (17: both flags listed and off; the
  recorder lays a phrase at its moment, pads silence, appends what would overlap and says where it lies, notes a
  skip, closes the file, writes nothing after the end; **in the pipeline: asked with the flag off, or the flag on
  without the ask, no folder, no wav and no row anywhere under the data folder, and a viewer is sent the same
  messages in all three cases**; with both, the rows equal the pipeline's own timings and the track holds every
  byte that went out; a phrase nobody hears is a skip row without text; the route ignores the ask with the flag
  off and answers the same fields; the picture's numbers from rows, and none made up for a session without a
  video clock; placement; the track cut and laid; the captions file, one caption at a time; the three stereo
  graphs; **a real render with ffmpeg of a small made-up video played twice with a lead and a gap: size,
  duration, and each ear's sound where it should be**; listening routes 404 and nothing written with the flag
  off; no pairs and no answers; blind (no system and no file name in what the page gets), shuffled per listener
  and fixed for one, answers counted per system, the last answer counts, bad answers refused; a manifest entry
  that cannot be played blind is left out, a path out of the folder among them; the pairs folder built from two
  folders). Website: `npx tsc --noEmit` clean.
- **v0 after this workstream:** all nine checks ok (`scripts/v1/v0-check.sh`). Port 8120 no longer answers
  (stopped through its task). 8111-8115 were not touched and still run (item 24 of `NEEDS_APPROVAL.md`).
- **Used:** one Live session of 85 s (hosted speech-to-text hears first in a GPU-engine session; two stock lines
  and the voice sample's check on the hosted voice; the rest on our GPU).
- **Test by hand:** v1's `backend\.env`: `V1_LIVE_RECORD=true`, `V1_LISTEN_TEST=true`; restart the backend (and
  the website needs a build with these pages). `/live`: the tick is under the engine choice. After the session:
  `data-v1\recordings\<session>\`, then `scripts\v1\render-pitch.ps1` (`RUNBOOK.md` section 3). `/listen-test`
  says there are no pairs until `data-v1\listen\pairs\manifest.json` exists.
- **Roll back:** both flags to `false` (the defaults) and restart. Recordings and answers stay in the data
  folder until deleted by hand; with the flags off nothing reads or serves them.

### Decided, and what to watch

- The example was recorded with `V1_LIVE_BUDGET` on and in Punjabi only: the setting and the language the WS1
  measurement recommends, one language to keep the hosted use to one short session.
- "On time" on the picture is the definition used everywhere else in v1 (within 0.25 s), with "within 1 s"
  beside it, both labelled; not one unlabelled percentage.
- A recording is never deleted by itself, and deleting a voice profile does not delete recordings made in that
  voice. It is the speaker's (copied) voice and their words. Until there is a rule, keep the flag off except for
  a session whose speaker has agreed to the video being made (`NEEDS_APPROVAL.md` item 25).
- Viewers on `/watch` are not told that a session's dub is being kept. Nothing of theirs is in it (no chat, no
  viewer data), only the dub they are sent.
- The listening page has no sign-in, like the rest of the site: anyone who can reach it can answer, and one
  person can answer as several by clearing the browser's storage. Fine for a test among people you asked;
  not a public poll.
- The pitch video is 35 MB for 82 s (quality setting crf 21). The repository's hooks refuse files over 10 MB and
  video files are ignored anyway; it stays in the data folder.

## v1.1 WS6: cleanup (25 Nov 2026)

Two flags and their code are gone, and there is a recommended set of flags for v1's env file. No Live session,
no Studio job and no comparison backend was run: nothing was measured in this workstream, every number below is
quoted from an earlier entry. No flag was added. Nothing of v0 was touched.

### Removed: `V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE`

- **Why.** Neither earned its keep (Phase 5 above, `EVAL_REPORT.md` section 1.3).
  Translation ahead: 4-6 early translations started a run, none used, in 5 runs; partials arrive about 470 ms
  apart, so a pause is only certain when the final is arriving anyway; it cost 4-6 extra translation calls a
  language a minute. Fixed rules first: 61.4% of prompt tokens came from the server's cache with the flag off and
  with it on (40 calls each), call p50 379 ms against 420 ms: the cache was already on and already held each prompt.
- **What went.**
  `app/config.py`: `v1_spec_translate`, `v1_llm_prefix_cache`, and the setting `v1_spec_stable_ms`.
  `app/v1/flags.py`, `tests/conftest.py`, `scripts/v1/ab-server.sh` and `.ps1`, `backend/.env.example`: the two names.
  `app/live/pipeline.py`: the tracker and its table of early translations, the hooks at a partial, between
  partials, when a phrase goes out, at the translation call and at the end of a session, and the three helpers
  `_spec_kw`, `_spec_start`, `_spec_result`.
  `app/v1/phrase.py`: `SpecTracker`; `rest_of` and `DynamicPhraser.rest`, which only it used. `same_words` stays:
  the HQ transcript step uses it.
  `app/providers/llm_local.py`: the reordered rules and temperature 0.1; the prompt and temperature 0.2 of the
  flag-off path are what is left, unchanged.
  Trace and numbers that existed only for them: `spec` on a phrase record, `spec_started`, `spec_used`,
  `spec_dropped` and `partial_gap_ms` on `live_session_end`, the `spec_miss` event; `translated_ahead`,
  `ahead_started`, `ahead_used`, `ahead_dropped` in the Live summary (`app/v1/metrics.py`) and in the columns of
  `eval/v1/live.py`. Old trace files in `logs/` still hold those fields; nothing reads them any more.
  `eval/v1/prefix.py` (the script that measured the prefix cache): deleted.
  Tests: the three `SpecTracker` tests, the two pipeline tests of translation ahead, and the default-off case for
  the flag. Docs: the two rows in `RUNBOOK.md`; `SUMMARY.md` and `EVAL_REPORT.md` now say "removed"; the flag
  list quoted in `ARCHITECTURE.md`.
  Not edited: the earlier entries of this file (they are the record of what was measured).
- **An env file that still sets them.** `Settings` is declared with `extra="ignore"`: a name it does not know is
  skipped, in the env file and in the process environment alike. The backend starts, the name switches nothing
  on, and nothing warns about it. Checked two ways: a test loads an env file holding all three removed names, and
  the settings and the app were loaded once against this checkout's own `backend/.env`, which still holds one
  of the three names (counted by name, values not read; the file was not edited). The line can stay or go.
- **To get them back:** the commit before this one, `bc48922` (`git show bc48922:backend/app/v1/phrase.py`, and
  the same for `app/live/pipeline.py`, `app/providers/llm_local.py`, `eval/v1/prefix.py`, `tests/test_v1_phrase.py`).

### Recommended flags for v1's `.env`

Written out flag by flag, with the measured reason for each, in `RUNBOOK.md` section 3; short form in
`SUMMARY.md` section 2; a ready block as comments at the end of `backend/.env.example`. Code defaults stay off
and `backend/.env` was not edited: the flags take effect when the user copies the lines and restarts 8110.

- On, as asked: `V1_TRACE`, `V1_ROUTER`, `V1_API_LOG`, `V1_STUDIO_HQ`, `V1_FIT_115`, `V1_LIVE_STOCK_DEFAULT`.
- Where the reports and that list pull apart (said in the docs, not hidden):
  1. `V1_STUDIO_HQ` without `V1_HQ_REVIEW`: WS3 found HQ dubbing two of three test videos from a damaged
     transcript without it (25 of 38 lines against 0). The ready block switches `V1_HQ_REVIEW` and `V1_HQ_JUDGE`
     on with HQ.
  2. `V1_LIVE_STOCK_DEFAULT`: every v1.1 Live number was measured with a voice learned from the stream; with
     this flag a `/live` session without a streamer profile never learns one. The only v1 runs in stock voices
     (Phase 5, two languages, 3 runs) had first audio p50 5.1 s and 58.3% within 1 s, against 2.34 s and 83.3%
     with the learned voice. The budget was not measured with stock voices.
  3. `V1_BREAKER` + `V1_LIVE_DEGRADE` are not on the list and WS0 argues for them (4 of 22 phrases dubbed
     through a 50 s stall with them off, all of 23-24 with them on). Commented in the ready block: the user's call.
  4. `V1_LIVE_BUDGET` is recommended by WS1 for Punjabi-like languages but is one switch for every language, and
     Tamil loses content with it. Commented in the ready block.
- Also written down: `V1_FIT_115` acts on standard Studio jobs too, and was only measured inside HQ runs on
  videos that hardly needed speeding up; `V1_API_LOG` writes under `logs/api/` inside the repository and its
  cost per request was never measured.

- **Tests:** 287 pass, 1 skipped (was 292 + 1: six tests of the removed code went, one is new).
  New: `test_removed_flags_are_gone_and_an_env_file_that_still_sets_them_is_read` in `tests/test_v1_phrase.py`.
  The flags-off tests of every other workstream pass unchanged.
- **v0 after this workstream:** all nine checks ok (`scripts/v1/v0-check.sh`).
- **Not done here, for whoever restarts 8110:** the running backend still has the old code until it is restarted.
  `NEEDS_APPROVAL.md`, `MODELS.md` and `gpu_engine_v1/` were left alone (another workstream is editing them);
  neither document named a removed flag at `bc48922`.
- **Roll back:** `git revert` of this commit brings both flags and their code back, off by default.

## v1.1 WS5: GPU upgrades prepared for the user to deploy (25 Nov 2026)

Built on the laptop, on branch `v1-ws5`, beside another workstream that was using the GPU: so no Live session, no
Studio job, no comparison backend and nothing on the GPU machine. This workstream is scripts, unit tests and
documents; every step that needs the machine is in `NEEDS_APPROVAL.md` with its commands. No new flag: nothing in
the backend's behaviour changed.

- **Deploy kit** (`gpu_engine_v1/deploy/`, new): `kit.py` (Python 3.8+, no packages) with the wrappers
  `start.sh`, `smoke.sh`, `stop.sh`, `status.sh`, and one requirements file per server. A server is three
  commands: copy the folder, `start.sh <server>`, `smoke.sh <server>`. Servers: `qa` 9045, `tts` 9041, `maya`
  9042, `transcribe` 9043, `big-llm` 9044 (`--size 12b|31b`). No Docker and no sudo: one Python environment per
  server under `.venvs/` (or `--python` for an existing interpreter); the big model is started with the `vllm`
  program v0's server was installed with, which is only run.
  - `start` reads `nvidia-smi` first and refuses unless free minus need is at least 4 GB, again after the
    environment is built; refuses when the port already answers; says whether CUDA MPS runs and never touches
    it; knows only ports 9041-9045.
  - `smoke` prints PASS or FAIL per check with its time, then the GPU memory the server holds (its processes in
    `nvidia-smi`, and free before the start against free now) and one `RESULT` line; exit code 0 or 1.
  - `stop` ends only the process in the kit's own pid file, after checking its command line still carries the
    kit's port; a stale pid file is removed and nothing is stopped.
  - Needs in the table (GB): qa 0, tts 4, maya 9.2, transcribe 10, big-llm 14 (12B) and 27 (31B). **None was
    measured**: estimates and the model cards' figures; `--need-gb` takes a measured one.
- **QA server** (`gpu_engine_v1/qa_server.py`, changed): runs on CPU with no GPU memory (the kit starts it with
  no CUDA device visible); `QA_HEAR=0` leaves the speech-to-text out, `QA_THREADS` limits CPU threads (default 4).
  Speaker model: licence checked on its page (Apache-2.0, `MODELS.md`); the server now loads a speaker model only
  when it is listed as checked and open to commercial use, refuses ECAPA2 and unlisted models, says so in
  `/health`, and still scores words. New `POST /similarity` (two clips, the speaker model alone). `/health` has
  the licence, whether the model is loaded, and the average time of a comparison. The stub answers as before.
- **Voice A/B kit** (`gpu_engine_v1/ab/maya_ab.py`, `voice_lines.tsv`, new): 20 fixed lines (6 English, 4 Hindi,
  4 Tamil, 3 Bengali, 3 Punjabi) through IndicF5 on 9001 and Maya 2 on 9042 in one voice. The voice comes only
  from a profile in the store with consent on record; there is no other way to give it a sample. Writes
  `indicf5/<id>.wav`, `maya/<id>.wav`, `pairs/<id>_a.wav`, `<id>_b.wav`, `pairs/pairs.json` (which system is A is
  drawn per pair, seeded) and `timing.json`. Refuses while a stream is live. The run needs Maya on the machine.
- **Translation A/B** (`backend/eval/v1/llm_ab.py`, `translate_lines.txt`, new): 40 fixed lines (the 24 class
  lines of the hard set and 16 stream lines) into Tamil, Bengali and Punjabi with the product's own prompt; `run`
  per model (the two need not be loaded together), `sheet` (blind CSV and markdown, the key kept apart, the
  countable checks), `verdict` by a rule fixed in the file before any result: preferred in at least 60% of at
  least 40 decided pairs, in no language under 50% of at least 10, no more wrong-script or Latin lines and no
  empty one, median length at most 1.10 of the small model's, median at most 2.0 s a line in batches; fitness
  for Live (0.6 s median, 1.0 s p95) is reported beside it. 31B only if 12B wins.
- **Backend on the machine** (`scripts/v1/vm-backend.sh`, new; `scripts/v1/run-local.sh`, `V1_SKIP_WEB=1` added):
  fits the copied `.env` to the machine (data folder, ffmpeg) and starts the backend alone; the website stays on
  the laptop behind one forwarded port. Syntax-checked, never run.
- **`NEEDS_APPROVAL.md`** is now one ordered checklist of 24 items in six parts (the backend on the machine first;
  then the machine without GPU memory, with GPU memory, hosting, laptop only, yours), each with what, why, the
  written-out `ssh` and `scp` lines, the card's numbers, the MPS rule, verify and roll back, and a table from the
  old numbers to the new. Other documents still cite the old numbers; the table translates.
- **`MODELS.md`**: what was read on the pages on 25 Nov 2026 for the 12B and 31B checkpoints and the speaker model,
  and what could not be verified.

**Numbers (measured in this work):**

| What | On what | Runs | Result |
|---|---|---|---|
| One speaker comparison on CPU, two clips of 7 s | laptop CPU, 4 threads, the eval reel | 1 run, 20 comparisons | mean 765 ms, range 727-797 |
| The same, two clips of 3 s | as above | 1 run, 20 | mean 378 ms, range 343-440 |
| The same, another voice, 7 s each | as above | 1 run, 20 | mean 752 ms, range 700-831 |
| Similarity, same speaker / another voice | one pair each | 1 | 0.883 (7 s), 0.765 (3 s) / 0.142 |
| Speaker model load, first time with download | laptop | 1 | 38.8 s |

**Not measured, and why:** any server with its real model on the GPU, the GPU memory any of them takes, Maya 2
against IndicF5, the 12B model against the small one, the QA server's Whisper, the backend on the machine: all
need the machine, which this work was not to touch. The kit on Linux: it was written and tested on Windows; the
process-group and `/proc` parts run only on Linux and were read, not run.

**Found:**
- **31B does not fit by the estimates.** A window with the small translation model stopped leaves about 24 GB;
  27 GB plus 4 GB of headroom is 31.
- **The 12B checkpoint may not start on v0's vLLM.** Its page's discussion reports two start failures; one was
  fixed in the checkpoint, the other has no confirmed fix and no version is named as working (`MODELS.md`).
- **`gpu-mode.sh hq --run` without Docker would stop 9020 and then fail to start anything** (it starts the big
  model as a container, and `set -e` ends the script there, before its own way back). The checklist opens the
  window by hand instead and says not to use the script without Docker. The script was not changed.
- SpeechBrain's config reader fails with ruamel.yaml 0.19; `requirements.qa.txt` now pins below it.
- IndicF5 will be sent English lines as they are in the voice A/B (it has no English): those pairs are marked,
  and a refused line is listed as missing rather than hidden.

**Mistakes made in this work:** one command called `python` instead of the venv's interpreter, which on this PC
opens the Store stub and hangs; the task was stopped (it was this work's own). A first scratch environment for the
CPU run tried to install a second torch and failed on a long path; a second one took the big packages from the v1
venv through a path file and installed only the small missing ones, in the scratch folder. Nothing was installed
into the shared venv.

- **Tests:** 299 pass, 1 skipped (was 275 + 1). New: `tests/test_v1_ws5.py` (24: the memory rule on stand-in
  `nvidia-smi` output; the kit's ports are 9041-9045 and none that runs today, and its source holds no command
  that reaches past its own process; start refuses on a full card before any setup and writes nothing, for every
  server and for 31B; a dry run prints the commands and leaves no file; no `nvidia-smi` refuses a GPU server and
  lets the CPU one through; a port that answers is never replaced; argument parsing; the QA server gets no CUDA
  device; start, smoke and stop of a stub server on a free port with a bystander process left running; a stale
  pid file stops nothing; the command-line check; the smoke client passing and failing against fake servers,
  silent audio, a reply without Tamil letters, nothing listening, no `nvidia-smi`; the memory report; the 20 voice
  lines; the voice A/B refusing a profile without consent, writing same-named files and blind pairs, the same
  sides for the same seed, refusing while a stream is live; the translation set and rule; both models run
  through fake servers and a blind sheet that the key really describes; the verdict for a win, a narrow result,
  one weak language, too few votes, more unreadable lines, an empty line, too slow, too long; only a speaker model
  open to commercial use is loaded; comparing voices with a fake model; the stub as before).
- **v0 after this workstream:** see the hand-back of this work for `scripts/v1/v0-check.sh`. Nothing of v0 was
  edited, started or stopped; no Live session and no Studio job was made.
- **Test by hand (laptop, nothing loaded):** `backend\.venv\Scripts\python.exe gpu_engine_v1\deploy\kit.py status`
  and `... kit.py start tts --dry-run` (refuses on the laptop's own small card, with the numbers).
- **Roll back:** nothing runs. The QA server's old behaviour for an unlisted speaker model:
  `QA_SPK_ALLOW_NONCOMMERCIAL=1`.

## v1.2 Part 1: the founder's six decisions (26 Nov 2026)

What was asked: six decisions to apply exactly. `V1_MODE`, the removal of flags and `overrides.yaml` are Part 2 and
were not started. The backend on 8110 and the website on 3100 were not restarted: they run the old code until
they are, and the website needs a rebuild to show the recordings list and the viewer page's change.

### 1. `V1_HQ_ADAPTIVE` is on

- The four places now say **on** with one reason: against five takes of every line 61% less voice time (206 s
  against 524 s over three videos) with the same take kept on 76 of 76 lines; against v1's earlier rule (up to 4
  takes until one passes) the same number of takes (143), so it costs nothing. `V1_1_SUMMARY.md` section 3,
  `RUNBOOK.md` section 3 (flag table and recommended table), `SUMMARY.md` (flag table and recommended list),
  `backend/.env.example` (the value line and the ready block). The handbook's runbook, `OPEN_QUESTIONS.md`
  question 20 (closed), EXP-027 and `NEEDS_APPROVAL.md` item 27 point 1 follow.
- **The code's default is on too** (`v1_hq_adaptive` in `backend/app/config.py`): `.env.example`'s value line
  states the default, so the two had to agree. It is the first v1 flag whose default is on; it acts on HQ jobs
  only, so with `V1_STUDIO_HQ` off nothing changes. `tests/conftest.py` and the comparison-backend scripts still
  force it off, so earlier measurements and tests mean what they meant. Nothing was measured for this item.

### 2. HQ never runs without the review

- **Where HQ is decided:** `app/v1/hq/runner.py`, `is_hq` (the server's `V1_STUDIO_HQ` and the job's
  `quality=hq`). Inside that path the flag `V1_HQ_REVIEW` was read in three places: the transcript guard after the
  merge and clean steps, the cache key of the translation, and the choice between the rubric review and the plain
  one. All three now ask `app/v1/hq/review.py`, `required(settings)`, which is true whenever `V1_STUDIO_HQ` is on.
  So an HQ job is always reviewed and guarded, whatever the flag says; the flag has no effect on an HQ job any
  more. `GET /api/v1/flags` reports `V1_HQ_REVIEW` as in force whenever HQ is on.
- **Tests:** `test_hq_on_and_the_review_flag_off_the_review_still_runs` (a whole HQ job with the flag off: every
  line reaches the rubric reviewer, its edit is the line that is dubbed and is on record, the damaged transcript is
  put back, the plain review is not called; a standard job on the same server is not reviewed) and
  `test_review_is_required_whenever_hq_is_on`. Two older tests described HQ with the plain review and were
  changed to the rule, with the fake stages they share: the end-to-end job (its merged transcript is now put back by the guard) and
  "new flags off is as before", renamed "... but for the review".
- Not measured: nothing new. The numbers behind the decision are WS3's (25 of 38 lines damaged without the review
  in two of three videos, 0 with it).
- To watch: the review is a hosted-model call per language and job (WS3: 24 of 76 lines edited). When the hosted
  model is not configured the review goes to the routing file's `review` list, and when no answer can be used the
  lines stay as they were and the job says so in its warnings: "always reviewed" means always asked.

### 3. Live recordings: opt-in, 30 days, deletable

- Opt-in is unchanged (`V1_LIVE_RECORD` and the session's own tick; both tested in WS4).
- **New, `app/v1/record.py`:** `sweep` deletes every recording that ended more than `V1_RECORD_KEEP_DAYS` days ago
  (default 30, `0` = never by itself); age from `ended_at`, else `started_at`, else the newest file. It runs when
  the backend starts and in the half-hourly round that already deletes uploads (`app/main.py`), with the flag on or
  off, and never touches a session that is being recorded. `GET /api/v1/recordings` (session, dates, languages,
  size, the day it goes; no text, no sound) and `DELETE /api/v1/recordings/<session>` (404 unknown, 409 while it is
  still recording; a name, never a path).
- **Website:** `/live` handles recording (the tick), so the list is there: "Recordings kept on this server", one
  row a recording with a Delete button, shown whenever one exists; the tick's text now says how long a recording
  stays. Type-checked (`npx tsc --noEmit`), not looked at in a browser.
- **Deleting a voice profile, as the code is today:** `DELETE /api/voices/<id>` removes the sample file and the
  embedding and marks the profile deleted; a streamer's delete does the same and also removes the sample kept for our own voice engine.
  Neither looks at recordings, and neither could: a recording's `session.json` holds the session, languages, rate,
  engine and dates, no voice or streamer id. No rule was given for this, so none was built; a test writes the
  present behaviour down (`test_deleting_a_voice_profile_leaves_recordings_alone`). It stays open in
  `NEEDS_APPROVAL.md` item 25 and `OPEN_QUESTIONS.md` question 7.
- **Tests:** `tests/test_v1_record_keep.py` (12). ADR-0034.
- Also true: there are no accounts, so anyone who reaches the console can delete a recording; a video rendered
  into `data-v1\pitch\` is not a recording and is not deleted by the rule.

### 4. The hold comes back down

**Both ends were read first.** Server: `_note_late` grows `_sync_delay` and nothing ever lowered it. Viewer
(`web/app/watch/[id]/page.tsx`): the page pauses when its video is more than 0.8 s ahead of where it should be and
seeks when it is more than 3 s behind; in between it does nothing, and a dubbed phrase is timed against the
viewer's own video. So a smaller hold from the server alone would have left a watching viewer where they were
(in step with their picture, further behind live), as the older documents said. Both ends were changed.

**(a) Reproduced** (EXP-030; comparison backends 8120 and 8121, the WS0 relay, dense reel, Tamil, GPU engine, voice
learned from the stream; one session at a time, nobody live on 8010 or 8110):
- First try, the relay's hard stall (three stalls of 8 s, 1 run): the hold did **not** move (6.0 s throughout).
  13 phrases were skipped as too late, and a skipped phrase does not count towards growth; fewer than three of
  any six spoken phrases were late. A dead link loses phrases; it does not grow the hold.
- So the relay got a slow mode (every piece of data 700 ms later each way, connections kept): slow from second 60
  to 130. With the way back off, 2 runs: hold 6.0 s, five steps up during the slow spell, **11.0 s at the end of
  both runs** (180 s and 281 s after the link was back). That is the stream of 21 Nov.

**(b) Fixed.** `app/v1/hold.py` (`Ease`), called from `_note_late`: a step of 250 ms down when the hold is above
the session's starting value, nothing was late for 20 s (late = ready less than 750 ms before its moment, or
skipped, or the hold grew), three phrases were in time since and one since the last step, and the last step is 5 s
old. Never under the starting value, never without phrases, never for a streamer's YouTube offset. The viewer
page: after a `sync` message with a smaller hold it asks its player for 1.1x until it is within 0.05 s of its
place; its clock and the timing of queued phrases use the speed the player reports. Kill switch
`LIVE_SYNC_EASE=false` (default on): the server never lowers the hold and the page never speeds up.

**(c) Measured again, the same slow spell, way back on, 2 runs:**

| | Off (2 runs) | On (2 runs) |
|---|---|---|
| Highest hold | 11.0, 11.0 s | 10.75, 11.0 s |
| First step down after the link was back | never | 22.3, 23.5 s |
| Steps down, largest | 0 | 19 and 20, 250 ms |
| Hold when the run ended | 11.0 s (180 s after), 11.0 s (281 s after) | 6.25 s (171 s after; the material ended), 6.0 s (from 217 s after, kept 66 s) |
| Grew again after starting down | - | no, in neither |
| After the link was back: within 0.25 s | 67.1%, 70.1% (82, 127 phrases) | 65.5%, 57.9% (84, 133 phrases) |
| After the link was back: within 1 s | 97.6%, 95.3% | 96.4%, 95.5% |
| After the link was back: latest start | 1.05, 1.61 s | 2.57, 2.50 s |

Within 1 s is the same. Within 0.25 s is lower with the way back on in both pairs and the latest start later; at
two runs each that is not proven, but it is what a shorter hold should cost, and the on-figures are where these
sessions were at 6 s before the slow spell (53.8-61.5%). The way down paused three times for about 30 s in each
run, each time a phrase lacked 750 ms in hand.

**(d) Tests:** `tests/test_v1_hold.py` (11): the rule alone (nothing at the normal value; the wait, the step size,
the pace, the floor; a late phrase starts the wait again; a phrase without enough in hand counts as late; no
phrases, no step; one phrase in several languages counts once) and a session's hold (grows in a stall and eases
back to the starting value in steps, what viewers are told; does not ease while phrases are late and grows again;
kill switch off = only grows; a streamer's offset is never eased).

**Not verified, said plainly:**
- **No browser.** `web/` has no browser test set up (no Playwright in its packages), and the website could not be
  rebuilt (that would replace the build port 3100 serves). The viewer page's change is type-checked only. Whether a
  YouTube embed, and above all a live one, obeys `setPlaybackRate(1.1)` is not known. If it does not, a viewer who
  is already watching stays in step with their own picture and stays further behind live; new viewers join at the
  lower hold.
- Not measured: `V1_BREAKER` + `V1_LIVE_DEGRADE` on, more than one language, a real tunnel, a speaker who pauses.
- Comparison backends started after this work have the way back on unless `LIVE_SYNC_EASE=false` is passed: a
  "flags off" baseline's hold can now come down where it used to stay up.

**Found on the way:** in the hard-stall run (every flag but the router off) no phrase was produced after second 194
of 312 fed, and no error was reported: the last three phrases had captions and no sound. The four slow-mode runs
on the same two backends ran to the end. Hard stalls without the breaker and the ladder are the case WS0 built
those for; this was not looked into further.

### 5. Licences

Fetched on 26 Nov 2026 as raw files and public records; quotes and links in `MODELS.md`, "checked on 26 Nov 2026",
and `docs/handbook/MODELS.md`.
- **Silero VAD:** MIT (licence file; README "Published under permissive license (MIT)"). The README's badge shows
  MIT while its alternative text reads "License: CC BY-NC 4.0": a leftover, recorded.
- **Demucs:** the original repository is archived and points to its author's fork, "the officially maintained
  Demucs". Both licence files are the same MIT text. **But the fork's README says: "The license of the weights is
  not clear: MusDB contains some data that were only usable for research purpose."** So "Demucs is MIT" is true of
  the code only. Recorded as unsettled (`OPEN_QUESTIONS.md` question 13); the task expected a plain MIT.
- **IndicF5: legal confirmation needed.** Its record says `license: mit`; `dheeyantra/dhee-indic-f5` (fine-tuned
  from it, CC-BY-NC-4.0) says it "inherits non-commercial terms from its lineage" (F5-TTS trained on Emilia,
  CC-BY-NC-4.0; IIT-Madras data); F5-TTS's authors say their pre-trained models are CC-BY-NC. AI4Bharat's code
  repository has no licence file. Not fetched: IndicF5's card as a raw file (401, gated; the page itself was read
  through a page reader). Not known: whether IndicF5's weights began from F5-TTS's.
- `NEEDS_APPROVAL.md` item 28, "Get written confirmation of commercial use from AI4Bharat / legal review", after
  item 27; in its number table, in `V1_1_SUMMARY.md` section 4, in `SUMMARY.md` and the handbook's roadmap.
  `SUMMARY.md` no longer lists IndicF5 as "clear".

### 6. PITCH_FACTS

"Safe to say" row 1 is the 67-minute stream: 97% within 1 s, 1281 of 1327 spoken lines in the copied voice, first
audio p50 2.5 s / p95 5.1 s, with within 0.25 s 81% and within 2 s 98% beside it, as SPEC section 21 and EXP-016
give them. Conditions: one real stream, a YouTube quiz class, 67 minutes, 1363 phrases, Punjabi, one speaker, v0,
all-GPU mode, backend on the laptop, engines through the tunnel. Caveats kept and one added (the hold grew to 11 s
on that stream). Old rows 1 and 2 are rows 2 and 3 ("as row 1" became "as row 2"); rows 4-12 unchanged.

### Hand-back

- **Tests:** 336 pass, 1 skipped (was 311 + 1). New files `tests/test_v1_hold.py` (11) and `tests/test_v1_record_keep.py` (12); 2 new and 2
  changed in the HQ files.
- **Docs:** ADR-0034 (recordings), ADR-0035 (hold), EXP-030, two RESULTS rows, CHANGELOG, the handbook pages named
  above.
- **Comparison backends:** 8120 and 8121 were started from PowerShell and stopped; the relay on 8191-8193 was
  stopped. The five old ones on 8111-8115 were not touched.
- **Roll back:** `V1_HQ_ADAPTIVE=false`; `LIVE_SYNC_EASE=false`; `V1_RECORD_KEEP_DAYS=0` (never by itself). The
  review of HQ jobs has no switch by decision: do not offer HQ (`V1_STUDIO_HQ=false`).

## v1.2 Part 2: auto mode (26 Nov 2026)

What was asked: one setting, `V1_MODE=auto`, v1's default; in it nobody manages switches. Built and tested here;
**nothing in this part is a measurement**: two short sessions on one comparison backend were a smoke check
(below), and the comparison of auto against "budget on" is Part 3. The backend on 8110 and the website on 3100
were not restarted and the website was not rebuilt: both run the old code until they are. ADR-0036 (auto mode),
ADR-0037 (removed features), both drafts until Part 3's numbers are in.

### The resolver and the overrides file

- **`backend/app/v1/mode.py`** (new): `on(feature, settings)` is the single answer to "is this in force". `auto`
  (the default; anything but `manual`): the table `AUTO` in that file decides, the per-feature `V1_*` settings are
  not read, and `backend/config/overrides.yaml` may switch one behaviour off or pin a value. `manual`: every
  feature follows its own setting as before v1.2 and what v1.2 added is off. "HQ never runs without the review"
  lives in the same function. Every read of a flag in `backend/app/` now goes through it (the Live pipeline asks
  once, when a session's pipeline is built); `app/v1/flags.py` only reports.
- **`backend/config/overrides.yaml`** (new, every entry commented out) and `V1_OVERRIDES_FILE`. Read once. Missing:
  no overrides. Not readable, not a list of `name: value`, an unknown name or value: logged, that part ignored,
  the backend starts. Read in auto mode only. Entries: `RUNBOOK.md` section 3.2.
- **Always on in auto:** trace, router, API log, breaker, ladder, stock default, Studio HQ, HQ review, fit 1.15,
  adaptive takes, normaliser, job glossary (the founder's list). **Decided here, not on that list:** the HQ judge is
  on (the v1.1 reports recommend it with HQ); recordings are allowed (a session still has to ask); the two tool
  pages answer; the batching voice server, Maya, the late-line shortener and the live back-check are **not** part
  of auto (never measured alone, or not deployed) and can only be pinned on in the overrides file for a trial.
- `/api/v1/flags` is still there (mode, overrides in force, what is on). `tests/conftest.py` pins
  `V1_MODE=manual` with every flag off, so the suite of v1 and v1.1 means what it meant.

### Auto budget and the meaning check

- **`app/v1/dense.py`:** `AutoGate` (per language: budget on while the running mean of the backlog is over 500 ms
  [off under 200], the running mean of dub length over slot is over 1.15 [off under 1.05], or speech is dense; off
  only after 4 calm lines and not before 15 s), `WordRate` (source words a second over 30 s: dense over 4.0, until
  under 3.2; beside the speaking share's 70% / 60%), `MeaningRate` (below). For the gate "behind" is also a phrase
  whose turn comes after its own moment (sound made late: a slow voice, a stall); the controller keeps the backlog
  alone, as it was measured in v1.1.
- **`live/pipeline.py` `_translate`:** budget off for a language = the full prompt: no word limit, no "be brief",
  and v0's own word limit is not used either. Budget on = v1.1's budget, its scale from the controller (which now
  exists only here), at most 0.9 while dense, short lines joined to the next, speed-up at most **1.3x**
  (`V1_DENSE_MAX_TEMPO`; v1.1 measured 1.4x, which nobody has heard: decided here).
- **`app/v1/meaning.py`** (new) and `app/v1/guards.py` (new): every 3rd spoken line of a language while its budget
  is on (every 8th while off) goes into a queue of 6; one worker has up to 4 lines of a language judged in one
  model call, after they were spoken: `lost` (something that matters is missing) and `shift` (it says something
  different). A full queue or no answer is counted, never taken as a pass. The judge comes from
  `providers.get_judge`: the hosted model when one is configured (in a GPU-engine session that is another model
  than the translator), else the session's translator; a model call, so it never waits for or holds the hosted
  voice account's one request.
- **Loosening:** over 25% lost on at least 6 (of the last 12) judged budgeted lines: one step, 0.1 more of the slot
  (on top of the line's own room); the rate is then measured afresh; at 3 steps the language is translated in
  full. At or under 10% on 6 new lines, with the dub behind, 120 s after the last step: one step back; from "in
  full" one step back on trial after 120 s behind.
- **Logged:** trace `live_auto_budget` (on/off, why, backlog, dur_ratio, dense), `live_meaning` (per judged line:
  lost, shift, the rate, steps; no text), `live_budget_adjust`; a session's `/metrics`: `auto_budget`,
  `auto_budget_log`, `ratectrl`, `meaning`; per phrase `auto:<lang>`, `loose:<lang>`, `judged:<lang>`.

### The English voice

- `app/v1/warm.py` is now only this (`en_mode` for manual mode, `en_choice`, the probe line).
  `LivePipeline._en_start`, `_en_probe`, `_en_set`. Auto mode, every session with English (v1.1: GPU-engine
  sessions only): a voice pinned in the overrides file; else the stock voice when the session has no copied voice
  at its start (also when one is still to be learned from the stream); else **one probe line (11 words) in the
  hosted copy, timed**. Time a line has = the viewers' hold (6 s; 8.5 s for a hosted copy without our engine; a
  streamer's own offset) less `V1_EN_PIPELINE_MS` 3800 (the phrase, about 2.2 s, and its text, about 1.6 s: v1.1's
  figures). In time: the copy for the whole session. Longer, failed, or no answer in 6 s: the stock voice.
- Chosen once (`_en_set` refuses a second choice), stored on the session row (`en_voice`), in `/metrics`
  (`en_voice_choice`) and the trace (`live_en_voice`, with the probe's ms). The first English lines wait for the
  choice. A later change only by the ladder, per failing line, logged as `live_voice_fallback`.

### A refused line

- **`app/v1/voicechain.py`** (new): the one order, `gpu, copy, stock, stock_alt` (our engine's copy, the hosted
  copy, the language's stock voice, its other stock voice where it has two). Live: a hosted stock line refused
  before any sound is asked once more (v1.1 did that for English only); then the ladder's own step (copy to
  stock); then every voice of the order that was not asked. Only when all made nothing: `unspoken:<lang>` on the
  phrase, `unspoken` in the trace's phrase record and `/metrics`, a `live_voice_fallback` event with what each voice
  answered, an error line in the log and on the console. A line whose translation failed, or that fell to an
  error in the pipeline, is marked the same way (`untranslated`, `error: ...`).
- Studio: `stages/voice.py` `synth_line(..., fallback=True)` walks the same order; `NoVoice` when all fail; the
  runner then marks the line (`unspoken`, flagged, no audio), warns, traces `studio_unspoken` and **finishes the
  job** (manual mode: the job fails, as before). HQ the same around `best_line`.
- Auto mode only. In manual mode a refused line is still silent and unrecorded, as in v1.1 (kept so that a
  baseline is what it was).

### Guards

- **Script** (`guards.script_ok` = the translators' own `wrong_script`): every translated Live line; a failing
  line is translated once more (4 s at most), then spoken and flagged (`script:<lang>` 1 = put right, 2 =
  flagged). The transcript, when the session's source language has a script of its own: marked `src_script` 0
  (a transcript cannot be made again). It sees letters, not words.
- **Content shift, Studio** (`app/v1/lineguard.py`, new): every translated line is judged before the voice, in
  batches of 20; a failing line (`shift` or `lost`) is translated once more and judged again; passes: the new line
  is dubbed; fails again: the first line is dubbed and flagged ("needs your ear", with the reason). A line that was
  shortened to fit its slot afterwards is judged once more and only flagged. A line the judge did not answer for is
  `not_checked`. Standard and HQ jobs (HQ: after its review). Per job: `stage_timings._guards[<lang>]`.
- **Content shift, Live:** the `shift` answer of the same judged sample; counted, nothing made again.
- **In the eval outputs, each its own column:** `eval/live_replay.py` (script guard failed / flagged, transcript,
  content shift judged / found, meaning judged / lost / rate, spoken by another voice, no sound marked, no sound
  without a mark; per language too), `eval/v1/studio.py` and `studio_table.py` (script wrong / flagged, shift
  checked / not checked, wrong / flagged, shortened and flagged, no sound), `logs/sessions/index.csv` for sessions
  of auto mode. The tables say "every line" or "a sample" in the row's name.

### Removed (ADR-0037)

`V1_PHRASE_DYNAMIC` (`DynamicPhraser`, five settings), `V1_LIVE_NATIVE_SPEED` (its branch, two settings, the
`native` field), `V1_LIVE_WARMSTART` (the warm-up for every language and engine, the stored voice sent at session
creation, the pitch tracker and matched stock voice, the softened change of voice, two settings, the `open` /
`handover` marks, the `warm` block, two trace events), `V1_LIVE_RATECTRL` as a switch. Their tests went;
dense mode and the controller are tested again in auto mode. `V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE` had no
trace left in code. An env file that still sets any of them loads, in either mode (test). The last commit with the
code: `339589c`. Reports of measurements were not edited; `RUNBOOK.md`, `SUMMARY.md`, `V1_1_SUMMARY.md` (a note
and the rows), `docs/v1/ARCHITECTURE.md`, `NEEDS_APPROVAL.md` (the items that named the flags) and the handbook's
current-state pages were.

### What a user sees differently

- `/live`: with stock voices always on, the choice "the voice on this stream" and its consent tick are gone (they
  would do nothing); a paragraph says where a copied voice comes from. The recording tick stays (consent).
- `/health`: "How this server runs: automatic" instead of a list of switches. `/listen-test`,
  `/studio/calibrate`, `/metrics-ui`: their notices no longer name settings.
- Studio editor: a standard job's line can now be marked "needs your ear" (a guard, or no voice).
- The Engine choice and the HQ choice are untouched.
- Type-checked (`npx tsc --noEmit` passes); not looked at in a browser; **not live until the website is rebuilt**.

### `LIVE_STOCK_DEFAULT` always on: what it does to `/live`

Built as asked. In auto mode `POST /api/live/sessions` without a streamer profile drops `voice_from_stream` and
`voice_profile_id`: such a session **never learns the voice on the stream, with or without the consent tick**, and
every language is spoken by the hosted stock voices, which share the hosted account's one request at a time.
A streamer's own session (`/streamer`, recorded voice) is not touched. `live_stock_default: off` in the overrides
file is the way back. The replay harness creates exactly such a session (`--voice stream`, no streamer), so in
pure auto mode it measures stock voices; see the smoke check.

### Smoke check (n = 1 each; not a result)

One comparison backend, port 8120, `-Mode auto`, no overrides, GPU engine, dense reel, sync mode; nobody live on
8010 or 8110; 26 Nov 2026 about 13:05-13:20 UTC. Started twice (once more after one line of the gate was changed).

- **Punjabi + Tamil, 3 loops (85 s fed, 32 phrases, 64 lines):** mode `auto` in the session's end record. Budget
  went on for Punjabi at phrase 1 ("long": the first line's dub was 2.69 of its slot) and for Tamil at phrase 8
  ("dense": share 85%, 6.2 words a second); it never went off (speech stayed dense). 52 lines under the budget, 12
  in full. Meaning sample: 4 lines judged (2 Punjabi: both lost and shifted; 2 Tamil: neither); no adjustment (under
  6 samples). Script guard: 64 lines checked, 3 Tamil lines failed, none put right by the second translation (all 3
  flagged). No line unspoken, none silent without a mark, no fallback to another voice.
  **Timing was very bad:** 0 of 38 spoken lines within 1 s, first audio p50 9.7 s, 26 lines skipped as too late,
  the hold grew to 11 s, 0% copied voice. The session was stock voices only (the rule above). The hosted stock
  voice was slow in that hour: two single lines asked outside a session took 4.5 s and 7.1 s for 5.6 s and 4.2 s of
  audio (first chunk after 2.3 s and 1.8 s). One request at a time at that speed cannot follow two languages of
  dense speech. Whether anything in auto mode adds to it was not separated.
- **English + Punjabi, 1 loop (12 phrases):** `live_en_voice` once: stock, "the session has no copied voice for
  English"; stored on the session row. Budget on for both ("behind"). No line judged (fewer than 3 budgeted spoken
  lines a language). 10 lines spoken, 14 skipped as too late, none unspoken.
- Also seen: the link-stall detector opened the circuits of two voice-engine processes once ("health: timeout";
  their health answers took 1.4-1.6 s that hour against the probe's 2 s limit). Not used by these sessions.

### Not verified

- Every threshold of the auto budget, the meaning check and the English probe: first values, unmeasured.
- The budget going **off** again in a real session; a loosening step in a real session; the probe of a real copied
  voice (no session here had one at its start: that needs a streamer profile); a real refusal walking the order
  of voices; a Studio job in auto mode on real services; the content-shift judge's answers against a reader.
- Auto mode with a voice learned from the stream (`-Overrides "live_stock_default=off"`): not run.
- What the trace and the API log cost now that they are always on.
- The website's changes in a browser.

### Hand-back

- **Tests:** 347 pass, 1 skipped (was 336 + 1), exit code 0. New: `tests/test_v1_auto.py` (41: the resolver in both modes; the overrides file good, bad in four ways, missing, with unknown names, with a byte-order mark, and the shipped one; the gate on, off after calm lines and a minimum time, no flapping, long lines, dense speech; the word rate; the meaning rate loosening, measuring afresh, tightening, the trial step back; the sample and its queue; normal speech gets the full prompt and the budget comes on when behind; on and off in the trace; a phrase made late counts as behind; dense speech joins short lines and stays at 1.3x; a slow judge holds no phrase up and a lossy language is loosened; the overrides for the budget; the English voice measured, chosen once, stored; too slow, failed or silent copy; no copy, pinned, hosted engine, switched off; the ladder's step on failure; a refused stock line asked again and spoken by another voice; every voice failing; our engine to the hosted copy to stock and back; an untranslated line; the order in one place; the script guard; the transcript guard; the trace record and the summary; the Studio guard, an unjudged line, the order of voices for a Studio line, a whole Studio job in auto mode; stock voices on `/live`; manual mode builds nothing of auto). Changed: `test_v1_warm.py` (the English tests stay), `test_v1_dense.py`, `test_v1_phrase.py` (the removed names in an old env file, both modes).
- **For Part 3:** `RUNBOOK.md` section 3.5 has the commands. Auto as v1 runs:
  `powershell -File scripts\v1\ab-server.ps1 -Port 8120 -Name auto -Mode auto`; "budget on" as in v1.1:
  `powershell -File scripts\v1\ab-server.ps1 -Port 8121 -Name budget -Flags "V1_LIVE_BUDGET=true"`. **The two differ
  in the voice** (stock against learned from the stream) unless auto also gets
  `-Overrides "live_stock_default=off"` on a third backend; without that a difference cannot be put down to the
  budget.
- **Roll back:** one behaviour: its line in `backend/config/overrides.yaml`. All of it: `V1_MODE=manual`. The removed
  features: `339589c`.
- **Comparison backends:** 8120 was started twice from PowerShell and stopped; nothing answers there. The five old
  ones on 8111-8115 were not touched.

## v1.2 Parts 3-4: auto mode measured, documents closed (26 Nov 2026)

What was asked: prove auto mode against the best earlier flag setting on the dense reel and on the three Studio
videos, say where it is worse and why, then finish the documents. **No default and no threshold was changed.** The
backend on 8110 and the website on 3100 were not restarted: they run the old code until they are
(`V1_1_SUMMARY.md` section 6.7 has the commands). Full accounts: `docs/handbook/experiments/EXP-031` (Live) and
`EXP-032` (Studio); the tables for a quick read: `V1_1_SUMMARY.md` section 6.

### How it was measured

- Four comparison backends from PowerShell (`scripts\v1\ab-server.ps1`), every one with `LIVE_SYNC_ADAPT=false`
  (hold fixed at 6 s, as in v1.1 WS1): 8121 `p3-budget` (manual, `V1_LIVE_BUDGET=true`), 8120 `p3-auto` (auto, no
  overrides), 8122 `p3-auto-learned` (auto, `live_stock_default=off`), 8123 `p3-auto-learned-nobrk` (that and
  `breaker=off`, `live_degrade=off`). The fourth was not in the plan: after round 1 the third setting was as bad as
  the second, and the cause could not be told from the auto budget without it.
- `eval.live_replay`, dense reel 8 times, Punjabi + Tamil, GPU engine, 5 runs a setting, taken in turn. The harness
  awaits each session before it starts the next (checked in its code and in the session times) and asks 8010, 8110
  and the targets for live sessions before every run: nobody was live at any start. 13:27-14:46 UTC, 20 runs, 0
  failed. Then the three Studio jobs on 8120 (14:46-14:54), then two repeats (below), then the hearings.
- **Stalls.** The laptop's connection stalled in auto runs 4 and 5 (the hosted speech-to-text silent for 12.3 s and
  15.9 s, every GPU endpoint down for 26.8 s and 20.4 s). Both were marked and repeated as runs 6 and 7, each beside
  one more "budget on" run. No other run has a gap in the transcript over 4 s. The tunnel and the engines answered
  at every check; nothing was restarted.
- The hosted stock voice was timed outside any session between rounds (10 long lines a language, 13:27-14:45) and
  at the end (20 short lines).

### A. Live: the numbers

Mean (lowest-highest) of 5 runs as run:

| | Budget on (manual) | Auto | Auto, learned voice | Auto, learned voice, no breaker |
|---|---|---|---|---|
| Within 0.25 s | 79.1% (73.2-81.8) | 66.3% (57.4-75.1) | 69.6% (55.7-80.8) | 74.2% (72.4-76.6) |
| Within 1 s | 90.0% (87.4-94.0) | 82.4% (71.0-89.3) | 83.9% (72.1-90.9) | 88.5% (86.4-90.1) |
| dur_ratio p90 | 1.16 (1.13-1.19) | 1.20 (1.17-1.22) | 1.15 (1.04-1.26) | 1.16 (1.09-1.24) |
| Skips per 10 min | 3.0 (0-6.1) | 34.1 (0-113.8) | 22.1 (3.0-86.6) | 5.4 (0-11.9) |
| First audio p50 / p95 (ms) | 2675 / 4939 | 2980 / 5688 | 2965 / 5378 | 2767 / 4690 |
| Copied voice | 95.1% | 0% | 83.1% (50.9-97.3) | 97.0% |
| Unspoken (marked) / silent without a mark | not marked / 0 | 1 line in 5 runs / 0 | 0 / 0 | 0 / 0 |
| Script guard failed / flagged, a run | not run | 7.2 / 5.8 | 5.0 / 5.0 | 3.2 / 3.2 |
| Meaning sample: lost of judged, a run | not run | 11.4 of 49.6 (23.3%) | 10.4 of 55.0 (19.0%) | 8.6 of 58.0 (14.8%) |
| Budget loosened / tightened, steps a run | - | 3.2 / 0.2 | 2.4 / 0.4 | 1.6 / 0.4 |
| Lines under the budget | all | 93.0% | 94.1% | 96.2% |

Auto with the two stalled runs replaced: 66.8% (57.4-81.9) / 82.1% (71.0-92.3), skips 25.1 per 10 min. "Budget on"
is where v1.1 measured it (80.6% / 92.3% on 24 Nov), so the baseline holds.

- **The auto budget was on for 93-96% of the lines and never went off** once on (17 sessions): this reel is dense
  from start to end. The half of the rule that gives normal speech the full translation did not run.
- **Words heard back** (20 lines a language from runs 3 and 4, 40 a cell, as v1.1; corrected rule): Punjabi 91.3%
  budget on, 86.4% auto, 88.9% learned voice, 87.0% no breaker; Tamil 86.3%, 83.5%, 83.8%, 87.1%. By v1.1's count:
  86.2 / 85.3, 82.7 / 79.7, 84.0 / 83.3, 83.1 / 83.1. The two runs of a cell differ by up to 10.5 points: no
  difference is shown.
- **Meaning on 20 lines a language** (run 3, phrases 37-56; read by the author of this report, not a native
  speaker, the reader and rule of v1.1's "7 of 20"): lost or wrong, Punjabi / Tamil: budget on 4 / 7, auto 9 / 6,
  learned voice 4 / 10, no breaker 3 / 10. The session's model judge on the same lines: 1 / 5, 5 / 8, 3 / 8, 0 / 3.
  Auto does not lose less than "budget on" in these lines; where a language had reached the second loosening step
  the lines read complete.

### C. Where auto is worse, and why

1. **Stock voices on `/live` (`LIVE_STOCK_DEFAULT`, on the always-on list): the largest cause.** Every line of a
   session without a streamer profile waits for the hosted account's one request. A line in a stock voice started
   within 1 s 48-83% of the time in every setting, a line in the copied voice 87-91%. From translation to first
   sound: stock p90 2.1 s, p95 3.6 s, 37 of 876 lines over 4 s; copied p90 1.2-1.5 s. The hosted voice's speed
   changed through the afternoon (one long line: 1.1 to 7.3 s), and with it pure auto: 38 skipped lines in run 1,
   1 in run 7. The override line: `live_stock_default: off`.
2. **The breakers and the ladder on a link that hiccups.** With the learned voice back, the voice engines'
   circuits opened 13 times in 3 of 5 runs (11 on one health answer over 2 s, 2 on one line over 4 s), about 34 s
   each; the ladder spent 119 s of 1056 s on the stock voice, which then queued as in point 1. The engine's own
   time was never over 0.62 s in those sessions. Without breakers the same afternoon cost 3-4 lines of 900 a wait
   over 4 s. WS0 measured the breakers in a 50 s stall; this is their first measurement without one.
3. **The meaning check loosens nearly every session.** 16 of 17 auto sessions, the first step on exactly 6 judged
   lines in 14 of 28 cases (2 lost lines are enough), while the judge calls 15-19% of budgeted lines lost before
   any step. A loosened language has more lines over their slots (Punjabi 40-45% against 16%). This is the 5
   points within 0.25 s that remain between the fourth column and "budget on".
4. Studio HQ: 152 s a video against 129-133 s on 25 Nov (the content-shift judge about 6 s, more takes about 11 s).

Not worse: Studio words heard back; lines without a record (none); the fourth column within 1 s.

**What was proposed and not done** (`NEEDS_APPROVAL.md` item 29): the override line for point 1; for point 2 either
the two override lines (no protection in a real stall) or slower settings (`V1_LINK_PROBE_TIMEOUT_S=4`,
`V1_BREAKER_VOICE_TIMEOUT_S=6`, `V1_BREAKER_OPEN_S=10`), or better a code change (two slow health answers in a
row); for point 3 `V1_MEANING_MIN_SAMPLES=12`. None of the proposed values was measured.

### B. Studio HQ in auto mode

One job a video on 8120 (auto, no overrides, empty data folder), Tamil + Bengali, GPU engine, voice from the video
with consent. The v1.1 rows are 25 Nov's jobs: another day.

| | HQ (25 Nov) | HQ + all flags (25 Nov) | HQ, auto mode |
|---|---|---|---|
| Words heard back | 95.9% (93.3-98.1) | 94.5% (93.2-96.5) | 95.6% (94.6-96.5); A / B / C 96.5 / 94.6 / 95.5 |
| Total time, A / B / C | 133 / 117 / 136 s | 140 / 129 / 130 s | 146 / 152 / 160 s |
| Voice stage, A / B / C | 73 / 67 / 79 s | 77 / 73 / 75 s | 74 / 93 / 92 s |
| Takes / flagged, of 76 | 143 / 15 | 156 / 21 | 178 / 20 |
| Damaged transcript lines | 0 / 13 / 12 | 0 / 0 / 0 | 0 / 0 / 0 |

Guards: script 76 checked, 0 failed; content shift 76 checked, 0 failed, 0 translated again, 0 flagged, 0 not
checked; nothing shortened; 0 unspoken. The 20 flagged lines are all the heard-back judge's (best of five takes at
67-89%). The review edited 21 of 76 lines. The content-shift judge is the model that had just reviewed those
lines: its "nothing found" is weak evidence. Target 96%: not reached.

### D. Bugs

- **Fixed:** `scripts/v1/collect-logs.py` wrote the two index tables from the stores named on its command line
  alone and dropped every other row (an earlier note said so; checked: true). It now keeps the rows and the column
  order of versions that were not named. Test `test_collecting_one_store_keeps_the_index_rows_of_the_others`.
  The four `p3-*` stores were then collected: 366 session rows and 37 job rows kept, 48 and 3 added.
- **Changed, a tool:** `eval.live_judge` counts each hearing by both rules (v1.1's and the corrected one).
- **Not a code bug, reported:** the script guard's second translation put right 7 of 77 failing Live lines; a Hindi
  word left in Devanagari inside a Tamil line is spoken as it is and flagged.
- **Seen, not looked into:** in the first stalled run one Tamil line was not translated at all (marked
  `untranslated`); the hosted fallback translated the 12 phrases after it.

### Part 4: documents

ADR-0036 (a "Measured" section, status, consequences) and ADR-0037 (what was measured after the removal); EXP-031
and EXP-032; `RESULTS.md` (13 Live rows, 4 Studio rows, 3 trend rows); `PITCH_FACTS.md` (rows 3, 8 and 9 say what
auto mode measured, five "Do not claim" lines; the 67-minute stream stays row 1; no new "safe" claim: nothing in
this measurement is better than what was already there); `CHANGELOG.md`; `V1_1_SUMMARY.md` section 6;
`RUNBOOK.md` section 3.1 and the handbook's runbook, onboarding and open question 1; `NEEDS_APPROVAL.md` item 29
(in its number table, `SUMMARY.md` and the handbook's roadmap); `logs/README.md` and the two index tables.

### Not verified

- Auto mode on normal-paced speech (the budget going off), with English (the probe, the one voice), with a streamer
  profile, on the hosted engine, with a hold that may grow.
- Any of the values proposed in item 29.
- A case where every voice fails, on real services; a Studio line a guard fails.
- The meaning judge and the meaning read against a speaker of Punjabi or Tamil.
- The website's changes of Parts 1-2 in a browser; the viewer page's catch-up at 1.1x.
- Auto mode with the backend on the GPU machine (no tunnel between backend and engines: the link whose hiccups are cause 2).

### Hand-back

- **Tests:** 348 pass, 1 skipped (was 347 + 1), exit code 0. New: the collector test.
- **Comparison backends:** 8120-8123 were started from PowerShell and stopped; 8120-8129 do not answer. The five
  old ones on 8111-8115 were not touched. `scripts/v1/v0-check.sh`: every line ok, exit 0.
- **Run data** (not in git): `data-v1/eval/v12/p3/` (24 run folders, `agg.json`, `heard.json`, `judge20.json`,
  `why.txt`, `stock.log`), `data-v1/eval/v12/studio/`, `data-v1/ab/p3-*/`.
