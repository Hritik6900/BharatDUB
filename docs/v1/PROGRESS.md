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
