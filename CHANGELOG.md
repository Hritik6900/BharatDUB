# Changelog

All notable changes to Bharat Dub are written here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); versions are named by tag or by the summary that
closed them. Numbers quoted below come from the documents named beside them; see
[docs/handbook/RESULTS.md](docs/handbook/RESULTS.md) for the measured results with their conditions.

**Flags.** Every behaviour added in v1 and v1.1 sits behind a flag whose default is off; with every flag off v1
builds the same providers and runs the same pipeline as v0. Since v1.2 Part 1 (26 Nov 2026) three things are on
without a flag being set: `V1_HQ_ADAPTIVE` (HQ jobs only), the review of every HQ job, and the viewer hold's way
back (`LIVE_SYNC_EASE`, a kill switch). Tests force every v1 flag off whatever the local env
file says. Recommended settings: `docs/v1/RUNBOOK.md`, "Recommended settings".

## [Unreleased]

### Added

- Documentation handbook added under `docs/handbook` (product, architecture, results, decisions as ADRs,
  experiments, incidents, runbook, history).
- `scripts/docs/gen_docs.py` (with `gen-docs.ps1`) regenerates the handbook's generated blocks: commit history,
  ADR and experiment indexes, result tables from `logs/` and `backend/eval/results.csv`.
- `scripts/docs/docs-check.py`: fails when a generated block is stale or code changed without a changelog entry.
- **v1.2 Part 1, kept Live recordings (ADR-0034):** a recording is deleted by itself `V1_RECORD_KEEP_DAYS` (30)
  days after it ended, checked when the backend starts and every half hour; `GET /api/v1/recordings` lists what
  is kept and `DELETE /api/v1/recordings/<session>` removes one; `/live` shows the list with a Delete button.
  Recording itself stays opt-in (`V1_LIVE_RECORD` and the session's own tick).
- **v1.2 Part 1, licences:** Demucs, Silero VAD and IndicF5's lineage read on their official pages on 26 Nov 2026
  and recorded with links in `docs/v1/MODELS.md` and `docs/handbook/MODELS.md`. IndicF5: legal confirmation
  needed (`docs/v1/NEEDS_APPROVAL.md` item 28). Demucs: code MIT, weights "not clear" by its maintainer.

### Changed

- **v1.2 Part 1:** `V1_HQ_ADAPTIVE` is on: the default in code and in `backend/.env.example`, and the same
  recommendation with the same measured reason in `docs/v1/V1_1_SUMMARY.md`, `docs/v1/RUNBOOK.md` and
  `docs/v1/SUMMARY.md` (61% less voice time against five fixed takes, the same take kept on 76 of 76 lines; the
  same 143 takes as v1's earlier rule). Tests and comparison backends still force it off unless asked.
- **v1.2 Part 1:** Studio HQ never runs without the review. An HQ job is reviewed against the rubric and its
  transcript guarded whatever `V1_HQ_REVIEW` says; `/api/v1/flags` shows `V1_HQ_REVIEW` as on whenever
  `V1_STUDIO_HQ` is on. Standard jobs are untouched.
- `docs/handbook/PITCH_FACTS.md`: the real 67-minute stream is row 1 of "Safe to say" (it was row 3), with its
  conditions spelled out; no number changed. One more line under "Do not claim" (licences).

### Removed

### Fixed

- **v1.2 Part 1, the viewer hold never came back down (ADR-0035, EXP-030).** After the hold grew during a slow
  link it now eases back to its normal value (6 s) in steps of 250 ms once phrases are ready early again, never
  under it and never while a phrase is late; `/watch` plays 1.1x after each step until it has caught up (not
  run in a browser). Kill switch `LIVE_SYNC_EASE=false`. Measured on a link slowed for 70 s, 2 runs each: hold at
  the end 11.0 s and 11.0 s without it, 6.25 s and 6.0 s with it.

### Security

- A kept recording no longer stays for good: 30 days, then deleted; any one deletable at once (ADR-0034). The
  delete call takes a recording's name only, never a path.

## [v1.1] - 2026-11-25

Built 24-25 Nov 2026 on branch `v1`. Detail: `docs/v1/V1_1_SUMMARY.md` and `docs/v1/PROGRESS.md`.
Tests: 311 pass, 1 skipped. v0 was not changed.

### Added

- **WS0 Never die** (`V1_BREAKER`, `V1_LIVE_DEGRADE`): circuit breakers on the GPU endpoints with a link-stall
  detector; a Live ladder from copied voice to stock voice, captions only, original sound, and back; the status
  page shows the A100 as unknown until the VM reports it; watcher lines for circuits and rungs; a tunnel watchdog
  script (not run). Through a 50 s stall, 4 of 22 phrases were dubbed with the flags off (1 run) and all with
  them on (3 runs). (`2cad302`)
- **WS1 Dense speech** (`V1_LIVE_BUDGET`, `V1_LIVE_RATECTRL`, `V1_LIVE_NATIVE_SPEED`): dub length against its
  slot (`dur_ratio`) and backlog per phrase in the trace; an expansion model per language; a duration budget for
  the translator with one shorter re-ask; a PI controller on the backlog; engine speed with a pace floor; a
  replay harness. With the budget, within 1 s of the moment rose from 86.5% to 92.3% on the dense reel (5 runs a
  setting, `docs/v1/LIVE_DENSE_REPORT.md`). (`5ec5f4c`, `ce156a8`)
- **WS2 Session start and English** (`V1_LIVE_WARMSTART`, `V1_EN_SINGLE_VOICE` with `V1_EN_VOICE=auto|copy|stock`):
  warm start per language and engine, a streamer's stored voice sent when the session is made, a stock voice
  matched to the speaker's pitch, a softened change to the copied voice; one English voice per session. Warm
  start showed no proven gain. (`0ec4418`)
- **WS3 Studio HQ** (`V1_HQ_JUDGE`, `V1_HQ_CALIBRATE`, `V1_HQ_ADAPTIVE`, `V1_HQ_NORMALISE`,
  `V1_HQ_AUTO_GLOSSARY`, `V1_HQ_REVIEW`): a judge order per language; old jobs scored again without making a
  voice line; a calibration page (`/studio/calibrate`); an adaptive number of takes; a number/date/currency
  normaliser for Hindi, Bengali, Tamil and English; glossary candidates from the transcript; a reviewed
  translation with a transcript guard. HQ words heard back 95.9% in the 25 Nov rerun (target 96%, not
  reached). (`93b5e75`)
- **WS4 Pitch kit** (`V1_LIVE_RECORD`, `V1_LISTEN_TEST`): a session's dub kept on disk only when the flag is on and
  the session asks for it; a side-by-side renderer (`scripts/v1/render-pitch.ps1`); a blind listening page
  (`/listen-test`) with its summary on `/metrics-ui`. (`bc48922`)
- **WS5 GPU upgrades prepared** (no flag; nothing deployed): a deploy kit for the v1 model servers (start, smoke,
  stop, status) that refuses unless 4 GB of GPU memory stays free; a voice A/B kit; a translation A/B kit with a
  written rule for a win; a QA server on CPU; the approval list as one ordered checklist
  (`docs/v1/NEEDS_APPROVAL.md`). (`ddb8d59` on `v1-ws5`, merged as `df27b93`)

### Changed

- The heard-back judge's counting rule no longer takes points off Bengali for a letter stored two ways (part of
  `V1_HQ_JUDGE`): on the same 23 Nov HQ output, 92.5% becomes 95.5% and flagged lines 25 become 15.
- Recommended settings written down in `docs/v1/RUNBOOK.md` and as a block in `backend/.env.example`. Code
  defaults stay off. (`e3128ef`)

### Removed

- **WS6 Cleanup:** `V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE` removed with their code, tests, trace fields and
  the prefix-cache eval script (no gain measured: 0 early translations used in 5 runs; cache share 61.4% both
  ways). (`e3128ef`)

### Fixed

- HQ without the review dubbed two of three test videos from a damaged transcript (25 of 38 lines); with
  `V1_HQ_REVIEW` a cleaned line that is no longer the line heard is put back (0 such lines). (`93b5e75`)

### Security

- The QA server refuses a speaker model whose licence is non-commercial (licence guard). (`df27b93`)
- Live audio stays unstored unless `V1_LIVE_RECORD` is on and the session itself asks; nothing deletes a recording
  by itself. (`bc48922`)

## [v1] - 2026-11-23

Built 23 Nov 2026 on branch `v1`, in a second checkout beside v0, which was not changed. Detail:
`docs/v1/SUMMARY.md`, `docs/v1/PROGRESS.md`, `docs/v1/EVAL_REPORT.md`. Tests at the v1 summary: 159 pass,
1 skipped.

### Added

- **Setup:** rules, settings and docs; commit hooks for this checkout only. (`92638c1`)
- **Phase 1, discovery:** a map of v0 and the build plan (`docs/v1/DISCOVERY.md`, `docs/v1/PLAN.md`). (`dcb3171`)
- **Phase 2, scaffold beside v0:** own ports (website 3100, backend 8110), own data folder and env file, flags,
  `GET /api/v1/health` and a `/health` page, compose file, start scripts; Live and Studio run end to end on the
  shared servers with every flag off. (`421d133`)
- **Phase 3, trace and numbers** (`V1_TRACE`): a record per Live phrase and Studio line (JSONL, Prometheus), a
  numbers endpoint and `/metrics-ui`; cost shown only for rates that are set (none are). (`7e96f13`)
- **Phase 4, provider router** (`V1_ROUTER`): provider order, timeouts and fallbacks per step from
  `backend/config/routing.yaml`; the shipped file builds the same providers as v0, checked for five setups.
  (`866aa45`)
- **Phase 5, Live changes** each behind a flag: dynamic phrase sizes, short-line merge, translation ahead,
  late-line shortening, back-check, session glossary, stock default, fixed-rules-first prompt; measured against
  each other. (`e2e9cca`)
- **Phase 6, new model servers** (`gpu_engine_v1/`, ports 9041-9045): batching voice server, Maya 2, Indic
  Transcribe, QA, big translation model; each with a stub mode tested through the backend's clients; a GPU mode
  script. No real model loaded (GPU memory, licences). (`bb71d9a`)
- **Phase 7, Studio HQ** (`V1_STUDIO_HQ`, `V1_FIT_115`): two hearings merged, cleaned transcript, translation with
  a word limit per line, review, numbers as words, takes scored and the best kept, flagged lines, sidechain
  ducking, loudness, jobs phase by phase; an editor with every take and a one-click swap. (`3654789`)
- **Phase 8, eval harness and report:** Live comparison across backends, Studio standard against HQ with every
  line heard back by one scorer, key words on the hard set. HQ words heard back 92.5% against 89.2% for standard
  (as reported on 23 Nov; corrected in v1.1). (`8608b97`)
- **Phase 9, operations:** demo check, warm-up through every service, backup script (no keys, dry run), runbook
  (start, checks, flags, GPU modes, roll back, restore); store and queue tests. (`01c9728`)
- v1 summary. (`5ed20d4`)

### Changed

- None of v0's behaviour: with every flag off, v1 builds the same providers and runs the same pipeline code.

### Fixed

- Every v1 flag is forced off in the test run whatever the local env file says (the phase 4 commit went out with
  one test failing for that reason). (`5908ec9`)

### Security

- Commit hooks refuse zips, files over 10 MB and assistant mentions in commits; the ignore rules for local tool
  settings are written as patterns. (`92638c1`)
- The backup script carries no keys. (`01c9728`)

## [v0-baseline] - 2026-11-22

v0, built 13-21 Nov 2026 on branch `main` and frozen at tag `v0-baseline` (`80c36d8`). It began as an entry for the
Gnani AI challenge (submitted 13 Nov) and the Vihaan X hackathon (14-15 Nov); since 21 Nov it is a startup product.
Detail: `SPEC.md` sections 16-21 and [docs/handbook/history/TIMELINE.md](docs/handbook/history/TIMELINE.md).

### Added

- **Scaffold and providers (13 Nov):** FastAPI backend, Next.js site, Supabase schema, hosted speech-to-text,
  voice and translation providers behind interfaces, smoke script. (`227f031`)
- **Studio (13 Nov):** pipeline stages 1-10 (extract, separate, segment, transcribe, translate, voice, fit, mix,
  render), job API with server-sent events, voices, glossary, a content-hash cache per stage; copying the voice
  from the uploaded video with consent; all ten languages. (`df1fa91`, `55d85d8`, `555e977`)
- **Live (13 Nov):** live pipeline, WebSockets for ingest, watch and chat, dashboard, mock providers, ingest
  client; voice learned from the stream with consent; sound from a browser tab; phrases cut from realtime
  partials. (`e4728b7`, `a7e7bb6`, `fac5189`, `2188ad3`)
- **Site (13 Nov):** landing, Studio, Live, voices, glossary and dashboard pages; design system v2. (`5f1d896`,
  `803f72c`)
- **Heard delay and sync mode (14 Nov):** silence trim, tempo fit, merged voice calls, heard-delay metric; sync
  mode with an adaptive hold; condensed translation while behind; eval script writing `results.csv`.
  (`a88de86`, `0b6d9f8`, `ecd2298`, `25e33b5`)
- **Copied voice on our own GPU (14 Nov):** IndicF5 on the A100 behind `GPU_VOICE_URL`, a pool of three engines,
  a self-reconnecting tunnel script, a word limit for the translator from measured pace. (`770112f`, `d911d2a`,
  `7fba6ab`, `87d0c78`)
- **Streamer Mode (15 Nov):** streamer profile, voice recorded once with the consent sentence read aloud, scored
  and stored; sessions that speak in it from the first phrase; YouTube delay offset; `/streamer` page.
  (`c401e5a`..`8d82653`)
- **Demucs on the GPU machine (15 Nov)** with CPU fallback. (`60ee40b`)
- **All-GPU mode (21 Nov):** speech-to-text (Whisper-Hindi2Hinglish-Apex) and translation (Gemma 4 E4B on vLLM) on
  our GPU machine beside the voice engines, hosted services as fallback; in Studio too. (`cc7fd39`, `bcee6aa`)
- **Engine per session and job (21 Nov):** an Engine button on Live, Streamer and Studio; the hosted engine stays
  the default. (`31673b9`)
- **Indic-Mio (21 Nov)** as a second voice behind `GPU_VOICE_MODEL=mio`; the default stays IndicF5. (`59fbbec`,
  `4f3d177`)

### Changed

- Site redesign (15 Nov): three-mode header switch, dark Studio pages, theme switch, new landing hero, streamer
  page like the live console. (`bc6a3e0`..`29aef48`)
- GPU machine replaced (20 Nov): engines rebuilt, CUDA MPS so three processes run at once; voice engine tuned
  (line length in letters, sample cut capped, denoising steps). (`0143cbd`, `59dbb97`)
- Voice engine about twice as fast (21 Nov): both guidance passes in one batch, MP3 instead of Opus. (`ada2272`)
- Product direction (21 Nov): no single-vendor rule, best measured provider per capability, no event framing.
  (`40f6183`)
- Live sync (21 Nov): phrase stamps fixed, the hold grows by at most 1 s at a time; voice steps per kind of voice;
  a slow copied voice is asked to speak faster (pace target 450 ms a word). (`a60b6d8`, `6667f1a`, `86188e5`,
  `b5807d0`, `e4bb35a`)
- Short lines stay in the one copied voice instead of a second voice (21 Nov). (`b151c39`, `94c8e90`)
- GPU speech-to-text holds back the last agreed word and decodes with beam 5; in the GPU engine the hosted service
  hears first with our model behind it (switch `gpu_stt_first`). (`be7540b`, `3a20c06`)
- `tunnel.ps1` opens one SSH connection per kind of traffic. (`9fae6c8`)

### Fixed

- Mobile overflow on Studio, voices, job and live pages. (`bfe093c`, `555e977`, `d917086`)
- A wrong PC clock is named in the console instead of a raw certificate error (15 Nov). (`89b68e4`)
- Viewer waits (pauses) on a live stream instead of seeking back, which a live embed ignores. (`71ca7cc`)
- After a tunnel drop the session returns to the GPU speech-to-text within 15 s instead of staying on the hosted
  one. (`fd93754`)
- Sessions left "live" by a restart are closed when the server starts. (`809ed4a`)
- A line's tail no longer repeats the words just dubbed. (`93b5c45`)
- The speech-to-text model's word for non-speech sound is dropped, also at the start of a line; its VAD uses one
  CPU thread. (`f6d4c50`, `ff3a162`)
- A stored voice's sample text is checked against the file and corrected when they differ. (`86188e5`)
- Tests no longer read the GPU engine's addresses from the local env file. (`405abd8`)

### Security

- No voice copy without recorded consent (HTTP 403); outputs labelled "AI-dubbed". (`df1fa91`, `55d85d8`)
- Only a sharing tab is captured for Live sound (no window or screen), so the dub cannot loop back. (`751375f`)

## References

| Version | Tag or commit |
|---|---|
| Unreleased | working tree after `e4944fd` |
| v1.1 | `e4944fd` (branch `v1`; WS5 on branch `v1-ws5` at `ddb8d59`, merged as `df27b93`) |
| v1 | `5ed20d4` (v1 summary) |
| v0-baseline | tag `v0-baseline` = `80c36d8` (branch `main`) |
