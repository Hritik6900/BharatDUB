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
