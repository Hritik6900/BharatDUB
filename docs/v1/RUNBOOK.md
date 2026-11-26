# v1 runbook

How to start, stop, check and roll back v1. v0 keeps running the whole time: nothing here stops or changes it,
except the HQ window (section 5), which pauses v0's small translation model and is run by hand.

Ports: v1 website 3100, v1 backend 8110, new model servers 9041-9045. v0: 3000, 8010, 9001-9040 (never bound,
only called).

## 1. Start and stop

**Without containers** (what was used to build and test v1):

```bash
cd /srv/bharatdb-v1/app
cp backend/.env.example backend/.env        # once: keys, DATA_DIR=/srv/bharatdb-v1/data, CORS_ORIGINS, PUBLIC_API_BASE
scripts/v1/run-local.sh                      # backend 127.0.0.1:8110, website 127.0.0.1:3100; logs in .run-v1/
scripts/v1/stop-local.sh                     # stops those two processes and nothing else
```

On Windows: `powershell -File scripts\v1\run-local.ps1`.

**With Docker** (written, never run: see `NEEDS_APPROVAL.md` items 2-4):

```bash
cp .env.v1.example .env.v1                   # ports, data folder, public address
docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 up -d --build
docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 --profile https up -d   # with a domain
docker compose -p bharatdb-v1 -f docker-compose.v1.yml down
```

Every service has `restart: always` and a health check, so after a VM restart the containers come back by
themselves. v0's model servers do not: start them with v0's own scripts (`start_live.sh`, `start_sep.sh`,
`start_llm.sh`, `start_stt.sh` in its engine folder), then run the warm-up below.

From a laptop, reach the site through SSH forwards of 3100 and 8110 (`ssh -L 3100:127.0.0.1:3100 -L
8110:127.0.0.1:8110 ...`), unless the HTTPS profile is up. A browser gives the microphone only to `localhost` or an
HTTPS page.

## 2. Check

```bash
scripts/v1/demo-check.sh          # READY / NOT READY: backend, website, every model server, hosted services, GPU, flags
scripts/v1/warmup.sh              # one small request through each service; prints each time
scripts/v1/v0-check.sh            # v0 is still fine (read-only)
scripts/v1/gpu-mode.sh status     # which model servers answer, free GPU memory, who is live
```

Pages: `/health` (green or red per service, the GPU machine's card when it reports it, else "A100 (VM): unknown",
circuit breakers, the mode the server runs in) and `/metrics-ui` (numbers from the
trace). Endpoints: `GET /api/v1/health`, `/api/v1/flags`, `/api/v1/routing`, `/api/v1/metrics/summary?hours=24`,
`/metrics` (Prometheus), `POST /api/v1/warmup`.

**When everything stops answering at once:** look at `data-v1/streamwatch/events.log`. `LINK STALL` with the hosted
services in the list means this PC was away (asleep), not the tunnel: all three stalls of 24 Nov 2026 were the
laptop in standby (`NEEDS_APPROVAL.md` item 17). `scripts\v1\tunnel-watchdog.ps1` (item 16) tells a sleeping PC, a
dead tunnel, a stuck ssh and a dead server on the GPU machine apart.

**Before a demo:** 15 minutes ahead run `demo-check.sh` and `warmup.sh`; the card must be in normal mode (not an HQ
window) and no other session live. One GPU through one address is one stream.

## 3. Mode, overrides, flags

### 3.1 Auto mode (v1.2; the default)

**Measured on 26 Nov 2026 (v1.2 Part 3): as shipped, auto mode is worse than manual mode with
`V1_LIVE_BUDGET=true` on dense Live speech** (66.3% against 79.1% of lines within 0.25 s, 82.4% against 90.0%
within 1 s, 34 against 3 skipped lines per 10 minutes; 5 runs each). The causes, the three lines that change it and
what each costs are in `NEEDS_APPROVAL.md` item 29 and at the end of this section. Studio HQ in auto mode is where
v1.1's HQ was (95.6% of words heard back) and about 19 s slower a video.

`V1_MODE=auto` in v1's `backend/.env`, and the default when the line is missing. Nobody manages switches:
`backend/app/v1/mode.py` is the one place that says what is in force (ADR-0036). The per-feature `V1_*` lines of
the table in 3.3 are **not read** in auto mode. `GET /api/v1/flags` shows the mode, the overrides in force and what
is on (a diagnostic for us; no page for users lists a switch).

| In auto mode | What happens | Not verified |
|---|---|---|
| Always on | the trace, the router, the API log, the breakers and the ladder, stock voices for a `/live` session without a streamer profile, Studio HQ on offer with its review, the 1.15x fit limit, adaptive takes, the normaliser, a job's own glossary, the HQ judge; a session that asks for it is recorded; `/studio/calibrate` and `/listen-test` answer | as each one's own entry in `PROGRESS.md` says |
| Auto budget | the Live duration budget of v1.1 applies to a language only while its dub is behind (backlog, running mean, over 500 ms; off under 200 ms), its lines come out longer than their slots (running mean of dub length over slot over 1.15; off under 1.05), or speech is dense (speaking share over 70% / under 60%, or over 4.0 source words a second / under 3.2). Off again only after 4 calm lines and not before 15 s. Outside that the translator gets the full prompt (no word limit, no "be brief"). While on: the controller of v1.1 scales it, at most 0.9 of the slot while dense, short lines join the next, speed-up at most 1.3x | every threshold is a first value and unchanged. Measured on the dense reel only: on for 93-96% of lines, never off again in 17 sessions; normal speech not measured |
| Meaning check | every 3rd spoken line of a language while its budget is on (every 8th while off) is judged by a model against its source, after it was spoken. Over 25% lost on at least 6 judged budgeted lines: that language's budget gets 0.1 more of the slot (a step); at 3 steps it is translated in full. At or under 10%, with the dub behind, 120 s after the last step: one step back | a sample, a model's opinion. Measured: about 50-58 lines judged in a 3.5-minute session of two languages, about one hosted model call a judged line; 15-23% judged lost; a language loosened in 16 of 17 sessions, the first time on 6-12 judged lines |
| English voice | sessions with English: a probe line in the copied voice at the start, timed against the hold less 3.8 s; in time: the copy for the whole session, else the one stock voice; no copy at the start: the stock voice. Chosen once, stored on the session (`en_voice`), in `/metrics` as `en_voice_choice` | one probe decides; the first English lines wait for it (6 s at most) |
| A refused line | a stock line refused before any sound is asked once more, then every other voice is asked in the order our engine's copy, the hosted copy, the stock voice, the language's other stock voice. Only when all fail: `unspoken` on the phrase, in the trace, the metrics and the log. Studio the same per line; the job finishes with the line marked | seen on real services: 24 lines spoken by the stock voice after our engine's turn failed, 2 stock lines asked again, 1 line marked unspoken (not translated); no line without sound and without a mark in 24 sessions. Every voice failing: fake providers only |
| Guards | script: every translated line (and the transcript when the source language is pinned), translated once more, then flagged. Content shift: Studio every line before the voice (translated once more, then flagged "needs your ear"); Live on the judged sample only, counted | the script guard sees letters, not words; the judge is a model. Measured: Live 77 of about 2830 lines failed the script guard (72 Tamil) and the second translation put 7 right; Studio 0 of 76 for both guards |

**What changes for `/live`:** with stock voices always on for a session without a streamer profile, "the voice on
this stream" is never learned and its consent tick has no effect (the rebuilt website no longer shows it). Every
v1.1 Live timing was measured with the learned voice; the only stock-voice runs were much worse (3.3, point 2).
To get the old behaviour: `live_stock_default: off` in the overrides file.

**After the measurement of 26 Nov 2026** (`docs/handbook/experiments/EXP-031-auto-mode-dense-reel.md`), what
changes auto mode on `/live`, each a choice for the founder (`NEEDS_APPROVAL.md` item 29); mean (lowest-highest) of
5 runs on the dense reel, Punjabi + Tamil:

| Setting | Within 0.25 s | Within 1 s | Skips per 10 min | Copied voice |
|---|---|---|---|---|
| Auto as shipped (stock voices on `/live`) | 66.3% (57.4-75.1) | 82.4% (71.0-89.3) | 34.1 (0-113.8) | 0% |
| ... with `live_stock_default: off` | 69.6% (55.7-80.8) | 83.9% (72.1-90.9) | 22.1 (3.0-86.6) | 83.1% (50.9-97.3) |
| ... and `breaker: off`, `live_degrade: off` (no protection in a real stall) | 74.2% (72.4-76.6) | 88.5% (86.4-90.1) | 5.4 (0-11.9) | 97.0% |
| Manual mode, `V1_LIVE_BUDGET=true` | 79.1% (73.2-81.8) | 90.0% (87.4-94.0) | 3.0 (0-6.1) | 95.1% |

**Settings of auto mode** (env names; first values, none changed after the measurement): `V1_AUTO_BEHIND_ON_MS=500`,
`V1_AUTO_BEHIND_OFF_MS=200`, `V1_AUTO_RATIO_ON=1.15`, `V1_AUTO_RATIO_OFF=1.05`, `V1_AUTO_WPS_ON=4.0`,
`V1_AUTO_WPS_OFF=3.2`, `V1_AUTO_MIN_ON_MS=15000`, `V1_AUTO_CALM_LINES=4`, `V1_DENSE_MAX_TEMPO=1.3`,
`V1_MEANING_SAMPLE_EVERY=3`, `V1_MEANING_IDLE_EVERY=8`, `V1_MEANING_WINDOW=12`, `V1_MEANING_MIN_SAMPLES=6`,
`V1_MEANING_MAX=0.25`, `V1_MEANING_LOW=0.10`, `V1_MEANING_STEP=0.1`, `V1_MEANING_MAX_STEPS=3`,
`V1_MEANING_TIGHTEN_AFTER_S=120`, `V1_MEANING_TIMEOUT_S=8`, `V1_MEANING_QUEUE=6`, `V1_EN_PROBE_TIMEOUT_S=6`,
`V1_EN_PIPELINE_MS=3800`. The controller and budget settings of v1.1 (`V1_RATECTRL_*`, `V1_BUDGET_*`,
`V1_DENSE_*`) are unchanged.

**Where to look:** a session's `GET /api/live/sessions/<id>/metrics` has `auto_budget` (per language: on, why, the
running backlog and dub length, steps loosened), `auto_budget_log` (every change), `ratectrl`, `meaning` (judge,
sampled, per language judged / lost / shifted / rate / steps, every adjustment), `guard` (script guard counts),
`unspoken`, `voice_events`, `en_voice_choice`. Trace kinds: `live_auto_budget`, `live_meaning`,
`live_budget_adjust`, `live_en_voice`, `live_voice_fallback`, `live_guard_script`, `studio_guard`,
`studio_unspoken`. A Studio job has `stage_timings._guards` per language; a flagged line shows in the editor.

### 3.2 The overrides file: switching ONE behaviour off

`backend/config/overrides.yaml` (or `V1_OVERRIDES_FILE`). Read once when the backend starts; every entry is
commented out as shipped. Remove the `# ` in front of a line and restart; put it back and restart to undo. Read
in auto mode only. A name or value that is not known is logged (`overrides: ... is not known and is ignored`) and
skipped; a file that cannot be read is logged and ignored as a whole; neither stops the backend.

| Entry | What it does |
|---|---|
| `trace: off` | no trace records; `/metrics-ui` and the reports go empty |
| `router: off` | providers from v0's fixed table instead of `config/routing.yaml` |
| `api_log: off` | no record per outbound request under `logs/api/` |
| `breaker: off` | no circuit breakers, no link-stall detector: every call waits for its own timeout |
| `live_degrade: off` | no ladder (copied voice, stock voice, captions only, original sound) |
| `live_stock_default: off` | a `/live` session without a streamer profile may copy the voice on the stream again, with the consent tick |
| `studio_hq: off` | HQ is not offered; every Studio job is standard |
| `hq_review: off` | **no effect while HQ is on**: HQ never runs without the review |
| `fit_115: off` | Studio speeds a line up by at most 1.35x (v0) |
| `hq_adaptive: off` | HQ makes up to 4 takes until one passes |
| `hq_normalise: off`, `hq_auto_glossary: off`, `hq_judge: off` | that HQ step as before v1.1 WS3 |
| `live_budget: off` | no duration budget at all: v0's word limit |
| `auto_budget: off` | the budget on every phrase, two steps by how far behind, no controller, no dense mode (v1.1's "budget") |
| `meaning_check: off` | no budget is loosened (lines are still judged for content shift unless that is off too) |
| `en_single_voice: off` | English chosen line by line again |
| `en_auto: off` | no probe: `V1_EN_VOICE` decides (`auto` there = the stock voice) |
| `en_voice: stock` or `copy` | pins the one English voice of every session; no probe |
| `voice_fallback: off` | a refused line is left without sound and without a record, as before v1.2 |
| `script_guard: off`, `shift_check: off` | that guard |
| `live_record: off` | no session can keep a recording |
| `hq_calibrate: off`, `listen_test: off` | that page and its routes answer 404 |
| `tts_server: on`, `tts_maya: on`, `live_late_shorten: on`, `live_backcheck: on` | not part of auto mode (off); `on` is for a trial. None was measured alone; the two servers are not deployed |

### 3.3 Manual mode: the flags as before v1.2

`V1_MODE=manual` and a restart: every feature follows its own line in `backend/.env`, all off by default except
`V1_HQ_ADAPTIVE`, and what v1.2 added (auto budget, meaning check, the measured English choice, the fallback to
another voice, the guards) is off. With everything off v1 behaves as v0. The overrides file is not read. This is
the mode of the comparison backends (`scripts\v1\ab-server.ps1`, `-Mode manual`, its default), of the test suite,
and of any baseline measured beside auto. What each flag does, and what was measured, is in `PROGRESS.md` and
`EVAL_REPORT.md`.

| Flag | On | Roll back |
|---|---|---|
| `V1_TRACE` | a record per Live phrase and Studio line; `/metrics-ui` fills | off: only logging stops |
| `V1_ROUTER` | providers from `backend/config/routing.yaml` | off: v0's fixed table |
| `V1_LIVE_LATE_SHORTEN` | a late line is said shorter instead of skipped | off: skipped as v0 |
| `V1_LIVE_BACKCHECK` | a dubbed live line is heard back by the QA server, made again if wrong | off |
| `V1_LIVE_STOCK_DEFAULT` | a Live session without a streamer profile speaks in stock voices | off: consent tick as v0 |
| `V1_TTS_SERVER` | copied voice from `V1_TTS_SERVER_URL` (:9041) | off: 9001-9003 |
| `V1_TTS_MAYA` | Maya 2 as a candidate voice in Studio HQ | off |
| `V1_STUDIO_HQ` | the HQ choice on `/studio` and `quality=hq` on a job | off: every job is standard |
| `V1_FIT_115` | Studio speeds a line up by at most 1.15x, then shortens | off: 1.35x |
| `V1_API_LOG` | one record per outbound provider request in `logs/api/<date>/<session or job>.jsonl` (no bodies, no keys) | off: nothing written |
| `V1_BREAKER` | circuit breakers on our GPU endpoints and the link-stall detector: a timeout, or 2 failures in 10 s, and the endpoint is not called for 30 s (the next provider answers at once); while a session is live every GPU endpoint is asked for its health every 5 s | off: every call waits for its own timeout, as v0 |
| `V1_LIVE_DEGRADE` | Live's ladder: copied voice, stock voice, captions only ("audio returning shortly" on `/watch`), original sound; back up by itself | off: as v0 |
| `V1_LIVE_BUDGET` | v1.1 dense speech: the live translator gets the phrase's own slot as words and letters (from the measured ms a word and a letter of this voice in this language), and an answer whose expected duration is over it by more than 15% is asked for once more, shorter | off: v0's word limit (`live_length_budget`) |
| `V1_EN_SINGLE_VOICE` | v1.1: English in a GPU-engine session is spoken in one voice for the whole session (`V1_EN_VOICE`: `copy`, `stock`, `auto` = stock), never chosen line by line. (Auto mode: every session with English, and the voice is measured, 3.1) | off: the hosted copy when 2 s are spare, else a stock voice |
| `V1_HQ_JUDGE` | v1.1 Studio HQ: a dubbed line is heard back by the best speech-to-text for its language (hosted first, then our GPU Whisper where it hears the language, which is Hindi only, then the QA server's Whisper once it runs), the next one when the first fails; the comparison treats the two ways of storing one letter as one spelling; every take, line and trace record says who judged it | off: the `score` list of the routing file and v1's comparison |
| `V1_HQ_CALIBRATE` | `/studio/calibrate` and its routes: label takes blind, agreement with the judge, a recommended flag line (`CALIBRATION.md`) | off: the routes answer 404, the page says it is off |
| `V1_HQ_ADAPTIVE` (default **on**) | one take of a line first; more, up to `V1_HQ_ADAPTIVE_MAX` (5), only while the best score is under `V1_HQ_ADAPTIVE_MIN` (0 = the flag line) | `false`: up to `V1_HQ_NBEST` (4) until a take passes |
| `V1_HQ_NORMALISE` | numbers, decimals, dates, clock times, the rupee and dollar sign, %, units and short forms are written out by rule in Hindi, Bengali, Tamil and English before the voice sees the line; abbreviations in capitals letter by letter for our own voice | off: the model-written step alone, as v1 |
| `V1_HQ_AUTO_GLOSSARY` | names, brands and repeated English terms found in a job's transcript are used as that job's glossary (never saved to the shared one); `GET /api/v1/jobs/<id>/glossary-candidates` | off |
| `V1_HQ_REVIEW` | the hosted model reviews every translated line against the written rubric (meaning, numbers and names, spoken register, fits the slot) and may edit; a cleaned transcript line that changed script or lost its English terms is put back. **Since 26 Nov 2026 every HQ job is reviewed whatever this flag says** (`app/v1/hq/review.py`, `required`); `/api/v1/flags` shows it as on whenever `V1_STUDIO_HQ` is on | none for an HQ job: HQ never runs without the review. To stop reviewing, do not offer HQ (`V1_STUDIO_HQ=false`) |
| `V1_LIVE_RECORD` | v1.1 pitch kit: a Live session **that was made with `record: true`** (the tick "Keep a recording of this session's dub" on `/live`, shown only while this flag is on) saves its dubbed sound, one track per language, and its phrase times and captions under `<DATA_DIR>/recordings/<session>/`. A recording is deleted by itself `V1_RECORD_KEEP_DAYS` (30) days after it ended; the list on `/live` and `DELETE /api/v1/recordings/<session>` delete one at once | off: the tick is not shown, the ask is ignored, nothing is written. What was kept earlier is still listed, still deletable and still deleted after its days |
| `V1_LISTEN_TEST` | v1.1 pitch kit: `/listen-test` and its routes: blind A/B pairs from `<DATA_DIR>/listen/pairs`, answers in `<DATA_DIR>/listen/results.jsonl`, summary on `/metrics-ui` | off: the routes answer 404, the page says it is off, the summary is not shown |
| `V1_STORE` | `postgres` (with `POSTGRES_DSN`) | `json` |

Not a flag but a setting: `LIVE_FIT_MAX_TEMPO=1.2` caps the Live speed-up at 1.2x (v0: 1.3).

Not a flag but a kill switch (v1.2 Part 1, on by default): `LIVE_SYNC_EASE=true`. After the viewers' hold grew (a
slow link) it comes back down to its normal value, 250 ms at a time, once phrases are ready early again:
`LIVE_SYNC_EASE_STEP_MS=250`, `LIVE_SYNC_EASE_EVERY_MS=5000`, `LIVE_SYNC_EASE_AFTER_MS=20000`,
`LIVE_SYNC_EASE_SPARE_MS=500`. `LIVE_SYNC_EASE=false` and a restart: the hold only grows, as before. A session's
`/metrics` shows `sync_eased` (steps down) beside `sync_grown`; the stream watcher prints every change as `HOLD a->b`.
Measured: `docs/handbook/experiments/EXP-030-hold-ease-back.md`. The viewer page's part (it plays 1.1x until it has
caught up) was not run in a browser, and needs the website rebuilt to be served at all.

**Removed.** `V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE` (v1.1 WS6) and, in v1.2 (ADR-0037),
`V1_PHRASE_DYNAMIC`, `V1_LIVE_NATIVE_SPEED`, `V1_LIVE_WARMSTART` and `V1_LIVE_RATECTRL` with their settings
(`V1_FIRST_PHRASE_*`, `V1_PHRASE_MIN_WORDS`, `V1_PHRASE_MAX_WORDS`, `V1_MERGE_UNDER_WORDS`, `V1_NATIVE_*`,
`V1_WARM_*`) no longer exist. A line that still sets one of them in `backend/.env` is ignored in either mode: the
backend starts as if it were not there. The controller of `V1_LIVE_RATECTRL` runs only inside the auto budget.

### 3.4 The measured reasons, flag by flag (written for v1.1 WS6)

**Since v1.2 nothing has to be set: auto mode is the default (3.1).** This list is kept because it holds the
measured reason behind each choice auto mode makes, and for whoever runs manual mode. Every number below is from
`EVAL_REPORT.md`, `LIVE_DENSE_REPORT.md` or `PROGRESS.md`; nothing was measured for this list. The ready block that
used to stand at the end of `backend/.env.example` is gone.

**On** (the list that was asked for):

| Flag | Why, and what is known about it |
|---|---|
| `V1_TRACE` | on in every measured run, no error from it; `/metrics-ui` and every report read it |
| `V1_ROUTER` | one run with it on: the same providers in the trace, first audio 2.4 s against 2.3-2.7 s with it off; the HQ path's provider lists and the breaker runs used it |
| `V1_API_LOG` | a log, not a speed or quality change; what it costs per request was not measured. It writes one line per outbound request (no bodies, no keys) under `logs/api/`, which is inside the repository: the folder grows with use |
| `V1_STUDIO_HQ` | a choice per job, not a change to standard jobs. Words heard back 95.9% against 90.6% for standard (three videos, one job each, rerun of 25 Nov, corrected counting rule), 128 s against 67 s. See point 1 below before offering it |
| `V1_FIT_115` | largest speed-up 1.15x in the HQ runs; the test videos hardly needed speeding up, so its effect on a video that does is covered by tests only. It acts on standard jobs too, not only HQ |
| `V1_LIVE_STOCK_DEFAULT` | a product rule, covered by a test, never measured as a timing change. With it on a `/live` session without a streamer profile speaks in stock voices even when the consent tick is set. See point 2 below |

**Every other flag:**

| Flag | Recommended | The measured reason |
|---|---|---|
| `V1_HQ_REVIEW` | **always on with `V1_STUDIO_HQ`: enforced in code since 26 Nov 2026, nothing to set** | without it HQ's merge and clean steps damaged the transcript of two of three test videos: 25 of 38 lines no longer the line heard, 0 with it. 24 of 76 lines edited by the reviewer. Words heard back 94.5% against 95.9% without it (the figure cannot see a damaged transcript); its edits were not judged by ear |
| `V1_HQ_JUDGE` | **on, with `V1_STUDIO_HQ`** | the counting rule no longer takes points off Bengali for a letter stored two ways: Bengali +5.6 to 6.3 points on the same output, Tamil unchanged, 25 flags become 15 |
| `V1_BREAKER` and `V1_LIVE_DEGRADE` | **on, both together** (not on the list above: point 3) | all three GPU endpoints stalled for 50 s: flags off (1 run) 4 of 22 phrases translated and dubbed; on (3 runs) 23, 24, 23 of 23, 24, 23, in a stock voice, first audio median 3.1-3.5 s. Healthy calls stayed far under the limits (slowest voice line 1.36 s of 4 s, slowest translation 1.13 s of 3 s). The stall was made with a relay, not a real tunnel |
| `V1_LIVE_BUDGET` | **on where Punjabi-like languages are the target; your call for Tamil** (point 4) | dense reel, Punjabi + Tamil, 5 runs: within 0.25 s 63.5% -> 80.6%, within 1 s 86.5% -> 92.3%, dub length over slot p90 1.42 -> 1.17, lines at 1.3x 46 -> 24 of 185; 15% fewer letters said; in Tamil 7 of 20 lines read had lost something that mattered |
| `V1_LIVE_RATECTRL` | removed in v1.2 as a switch (the controller runs inside the auto budget) | with the budget: 83.1% within 0.25 s against 80.6%, 91.8% within 1 s against 92.3%: inside the spread; it brings 1.4x on 15 lines a run, which nobody has heard |
| `V1_LIVE_NATIVE_SPEED` | removed in v1.2 | acted on 6.6 lines a run, all Tamil; no number moved |
| `V1_LIVE_WARMSTART` | removed in v1.2 | first audio p95 of the first 10 phrases 4.27 s -> 3.80 s over 5 runs each with the final build, 3.86 s -> 4.79 s with the first build, and "off" alone moved 0.41 s between batches: no proven gain. Its matched stock voice and softened change of voice need ears |
| `V1_EN_SINGLE_VOICE` | on with `V1_EN_VOICE=auto` only if English is a target and one voice matters more than the copied one; else off | English + Punjabi, 3 runs each: stock lines between copied ones 4.7 a session and 9 changes of voice with it off, none with it on. Every English line in the hosted copy: within 1 s 86.6% -> 73.7% |
| `V1_PHRASE_DYNAMIC` | removed in v1.2 | a session's first audio 5.9 s -> 4.1 s when a voice is ready at the start (stock voices); 5 points fewer phrases on time on dense speech (69.6% -> 64.5%, voice learned from the stream) |
| `V1_LIVE_LATE_SHORTEN` | off | skips 4.7 -> 1.7 a run, measured only inside a bundle whose timing was worse (56.0% on time against 69.6%); its own effect was not separated |
| `V1_LIVE_BACKCHECK` | off | not measurable: no scorer until the QA server runs (`NEEDS_APPROVAL.md` item 6); it does nothing without one |
| `V1_TTS_SERVER`, `V1_TTS_MAYA` | off | as of v1.1 WS4 neither server was loaded; nothing measured |
| `V1_HQ_ADAPTIVE` | **on** (decided 26 Nov 2026; the code's default) | against five takes of every line 61% less voice time (206 s against 524 s over three videos) with the same take kept on 76 of 76 lines; against v1's earlier rule (up to 4 takes until one passes) the same number of takes (143), so it costs nothing |
| `V1_HQ_NORMALISE` | off until a video with numbers has been heard | nothing to do on the three test videos (no digits); unit tests only |
| `V1_HQ_AUTO_GLOSSARY` | off (your call; harmless) | 16 names and terms proposed over three videos; its effect on the dub was not separated from the review's |
| `V1_HQ_CALIBRATE` | on when someone is going to label; it only adds a page | the page works on real takes; no labels yet, so no agreement figure |
| `V1_LIVE_RECORD` | off | not a speed or quality change; on only for a session whose speaker agreed to a video being made. A recording is deleted by itself after `V1_RECORD_KEEP_DAYS` (30) days and can be deleted at any time |
| `V1_LISTEN_TEST` | off until pairs exist in the data folder | no pairs and no ratings yet |
| `V1_STORE` | `json` | `postgres` was never run against a database |

Not a flag: `LIVE_FIT_MAX_TEMPO` stays at its default (phrases at the limit 20 -> 25 with 1.2; nobody has heard
1.2x against 1.3x).

**Where the reports and the list pull in different directions:**

1. **`V1_STUDIO_HQ` without `V1_HQ_REVIEW`.** The list switches HQ on and not the review. v1.1 WS3 found that HQ
   without it dubbed two of three test videos from a damaged transcript, and that the heard-back figure cannot
   see it. **Settled on 26 Nov 2026: HQ never runs without the review.** The code enforces it (an HQ job is
   reviewed and its transcript guarded whatever `V1_HQ_REVIEW` says; test
   `test_hq_on_and_the_review_flag_off_the_review_still_runs`). The ready block still switches `V1_HQ_JUDGE` on.
2. **`V1_LIVE_STOCK_DEFAULT` against the Live measurements.** Every v1.1 Live number (budget, controller, warm
   start, the breaker runs) was measured with the voice learned from the stream. With this flag on a `/live`
   session without a streamer profile never learns a voice, so those numbers describe Streamer Mode sessions and
   not `/live`. The only v1 runs in stock voices (two languages, three runs, flags off) had first audio p50 5.1 s
   (2.6-6.6) and 58.3% (45.5-81.6) within 1 s, against 2.34 s and 83.3% with the learned voice on the same reel:
   stock voices go through the hosted account one request at a time. The budget was not measured with stock
   voices. And a voice that is ready at the start is the one case where `V1_PHRASE_DYNAMIC` gained something
   (5.9 s -> 4.1 s to the session's first audio), so with stock default on that flag is worth a second look.
3. **`V1_BREAKER` and `V1_LIVE_DEGRADE` are not on the list, and their report argues for them** more clearly than
   for any other Live flag (4 of 22 phrases dubbed through a stall against all of them). The ready block has
   them as a commented line. What is missing is a real stalled tunnel and more than one language.
4. **`V1_LIVE_BUDGET` is one switch for the whole backend**, not per language: on, it shortens Tamil too, where
   the timing gain is the largest (58% -> 78% within 0.25 s) and so is the loss of content. It is commented in
   the ready block for that reason.

The two reliability flags belong together (measured together, `PROGRESS.md` v1.1 WS0). Their limits are settings:
`V1_BREAKER_TRANSLATE_TIMEOUT_S=3` and `V1_BREAKER_VOICE_TIMEOUT_S=4` (the whole time one live call may take on our
GPU before the next provider is asked), `V1_BREAKER_OPEN_S=30`, `V1_BREAKER_FAILS=2`, `V1_BREAKER_WINDOW_S=10`,
`V1_LINK_PROBE_EVERY_S=5`. `GET /api/v1/circuits` and the status page show every circuit; the stream watcher prints
`CIRCUIT OPEN / CLOSED / LINK STALL / LINK BACK` and `RUNG` lines.

The English-voice flag in manual mode (v1.1 WS2; measured in `PROGRESS.md`): `V1_EN_VOICE=auto` (the one stock
voice; `copy` = the hosted copy for every English line once the session has it; `stock`), `V1_EN_COPY_LEAD_MS=3500`.
A session's `GET /api/live/sessions/<id>/metrics` shows `en_voice` and `en_voice_choice`. On a night when the
hosted stock voice refuses lines (HTTP 502, "technical difficulties"): in auto mode a refused line goes to the next
voice by itself (3.1); to put every English line in the copy, `en_voice: copy` in the overrides file (manual mode:
`V1_EN_VOICE=copy`).

The Studio HQ flags of v1.1 WS3 all need `V1_STUDIO_HQ` and act on HQ jobs only. Settings beside them:
`V1_HQ_JUDGE_ORDER=prisma,whisper_gpu,qa_server`, `V1_HQ_JUDGE_BY_LANG=` (e.g. `hi-IN=whisper_gpu,prisma`),
`V1_HQ_BACKCHECK_MIN=0.9` (the flag line; the calibration page recommends a value once there are labels),
`V1_HQ_ADAPTIVE_MAX=5`, `V1_HQ_ADAPTIVE_MIN=0`, `V1_HQ_ADAPTIVE_SAME_STOP=false` (`true`: no further take once
two takes were heard back as exactly the same words; fewer takes, a little lower score), `V1_HQ_CALIBRATE_MIN_LABELS=30`, `V1_HQ_AUTO_GLOSSARY_MAX=40`.
`V1_HQ_TAKES_FIXED=5` makes every line five times whatever it scores: a measurement aid, not for normal use.
Review edits: sizes and the failed rule in the trace (kind `hq_review_edit`), the words in
`<DATA_DIR>/hq_review/<job>.jsonl` only. Old jobs scored again without making a voice line:
`python -m eval.v1.rescore --data <DATA_DIR> --jobs <ids> --out <dir>` (from `backend/`).
The Studio comparison of WS3: five comparison backends and `scripts/v1/eval-studio-ws3.sh` (its head says which),
then `python -m eval.v1.studio_table <out folder> --ab <data>/ab`.

The dense-speech flags (v1.1 WS1; measured in `LIVE_DENSE_REPORT.md`) have their numbers as settings:
`V1_BUDGET_SHARE=1.0` (the dub may take this share of the slot), `V1_BUDGET_OVER=1.15`, `V1_BUDGET_REASK_TIMEOUT_S=2.5`,
`V1_RATECTRL_KP=0.15`, `V1_RATECTRL_KI=0.03`, `V1_RATECTRL_SETPOINT_MS=250`, `V1_RATECTRL_MIN_SCALE=0.6`,
`V1_RATECTRL_RELAX_S=4`, `V1_DENSE_SHARE=0.70`, `V1_DENSE_OFF_SHARE=0.60`, `V1_DENSE_SCALE=0.9`,
`V1_DENSE_MAX_TEMPO=1.3` (1.4 in the v1.1 measurements; nobody has heard 1.4x), `V1_DENSE_MERGE_UNDER_WORDS=3`.
The controller and dense mode act only inside the auto budget (3.1). With the trace or the budget on, every Live phrase stores `dur_ratio` (dubbed seconds over the seconds of
its source slot) and `backlog` (how far the dub queue was behind the video); `/metrics-ui`, the session's
`/metrics` and the stream watcher's summaries show them. The model behind the budget starts from
`backend/config/live_expansion.json` (rebuild: `python -m eval.v1.expansion_seed`) and learns from every line.
Replay a recording through Live without YouTube, several settings in turn:
`python -m eval.live_replay <file> --out <dir> --target budget=http://127.0.0.1:8121 --target auto=http://127.0.0.1:8120 --runs 5`
(on Windows start the comparison backends with `scripts\v1\ab-server.ps1`; 3.5). Its table has the guards as rows
of their own: the script guard counts every line, the content-shift and meaning rows a judged sample.

The pitch kit (v1.1 WS4; `PROGRESS.md`). **A recorded session.** Live audio is never stored; the one exception
needs two yeses: `V1_LIVE_RECORD=true` on the backend and `record: true` on that session (the console tick; the
replay harness: `--record`). Then `<DATA_DIR>/recordings/<session>/` (or `V1_RECORD_DIR`) holds `session.json`,
`dub_<lang>.wav` (one continuous mono track per language on the session's clock, each phrase where a viewer's
player starts it) and `phrases.jsonl` (per phrase and language: `seq`, `t_speech_ms`, `media_s` = the video's time
it was spoken at, `start_ms` / `track_ms`, `dur_ms`, `late_ms`, `hold_ms`, `first_audio_ms`, `voice` copied or
stock, `tempo`, the caption `text`; or `skipped` and why). The stream's own sound is not kept. The caption text is
in that folder only: not in the trace, not in `logs/`.
**How long a recording stays** (v1.2 Part 1, ADR-0034): it is deleted by itself `V1_RECORD_KEEP_DAYS` days after it
ended (default 30; `0` = never by itself). The backend checks when it starts and every half hour while it runs,
whether or not `V1_LIVE_RECORD` is on at that time; a session that is being recorded is never touched.
`GET /api/v1/recordings` lists what is kept (session, dates, languages, size, the day it goes; no text, no sound);
`DELETE /api/v1/recordings/<session>` removes one at once (409 while that session is still recording), and `/live`
shows the same list with a Delete button whenever a recording exists. There is no sign-in on the site, so anyone
who reaches the console can delete a recording (as they can a voice). Deleting a voice profile does not delete
recordings: a recording does not say whose voice it holds.
**The side-by-side video** (original left, the same video with the dub right, captions, language, that
recording's own first-audio and on-time numbers):

```powershell
powershell -File scripts\v1\render-pitch.ps1 -Recording data-v1\recordings\<session> -Video C:\path\video.mp4 `
    -Lang pa-IN -Stereo split -Out data-v1\pitch\demo.mp4
```

`-Stereo split` = original sound left, dub right; `dub` = the dub alone; `mix` = the dub over the original at
18%. The source video must be the file the session was fed from, from its start. A recording made by the replay
harness also needs its `--lead-s`, `--loops` and `--gap-ms` as `-LeadS 6 -Loops 3 -GapMs 400`; a microphone
session (no video clock) needs `-OffsetMs` = the session time at which the video began. The numbers on the
picture are computed from `phrases.jsonl` of that recording and nothing else; a number it does not hold is left
out. Keep the output in the data folder: it is the speaker's voice and picture. To make one without YouTube:

```powershell
powershell -File scripts\v1\ab-server.ps1 -Port 8120 -Name pitch -Flags "V1_LIVE_RECORD=true"    # its own window (manual mode; in auto mode recordings are allowed without it)
cd backend; .venv\Scripts\python.exe -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\pitch `
    --target rec=http://127.0.0.1:8120 --runs 1 --loops 3 --langs pa-IN --record
# the recording is then in data-v1\ab\pitch\recordings\<session>
```

**The blind listening test.** `/listen-test` (auto mode: always there; manual mode: `V1_LISTEN_TEST=true`). Pairs live in
`<DATA_DIR>/listen/pairs/` (or `V1_LISTEN_DIR`) with a `manifest.json`:

```json
{"name": "what this set is (optional, stored with every answer)",
 "pairs": [{"id": "p0001", "a": "a/0001.wav", "b": "b/0001.wav",
            "system_a": "indicf5", "system_b": "other",
            "lang": "ta-IN", "text": "the words both clips should say"}]}
```

`id`: unique, letters, digits, `_`, `-`. `a` / `b`: clip paths inside the pairs folder (wav, mp3, ogg, flac).
`system_a` / `system_b`: who made each clip; never sent to the page. `lang` and `text` are optional. A pair with
a missing clip, a path out of the folder, a repeated id or the same system twice is left out. Build the folder
from two folders of same-named clips (the clips are copied under numbered names):

```powershell
backend\.venv\Scripts\python.exe scripts\v1\make-listen-pairs.py C:\clips\indicf5 C:\clips\other `
    --system-a indicf5 --system-b other --lang ta-IN --texts C:\clips\lines.json --name "IndicF5 against other, Tamil"
```

(`--texts`: `{"<file name without its ending>": "the line"}`; `--add` adds to an existing folder; a file name that
starts with a language code, `ta-IN_003.wav`, sets the pair's language.) A listener gets the pairs in an order
of their own, hears "first" and "second" (which system is first is fixed per listener and pair by a hash), rates
each 1 to 5 and says which they prefer or "no difference". Their id is a random string made by the browser; a
later answer for the same pair replaces the earlier one. `/metrics-ui` shows per system the mean rating, the
number of ratings and the share of stated preferences, or "No ratings yet". `GET /api/v1/listen/summary` is the
same as JSON. To start a new test, move `results.jsonl` away and replace the pairs folder.

### 3.5 Comparison backends: auto beside manual

A second backend on its own port (8120 or higher) and data folder (`data-v1\ab\<name>`), started from PowerShell
as a background task so that it can be stopped cleanly:

```powershell
# auto mode, as v1 runs (its own empty overrides file: backend\config\overrides.yaml is not read)
powershell -File scripts\v1\ab-server.ps1 -Port 8120 -Name auto -Mode auto
# auto mode with one behaviour switched off, e.g. the voice learned from the stream as in the v1.1 measurements
powershell -File scripts\v1\ab-server.ps1 -Port 8122 -Name auto-learned -Mode auto -Overrides "live_stock_default=off"
# manual mode (the default): every flag off but the ones given; this one is v1.1's "budget on"
powershell -File scripts\v1\ab-server.ps1 -Port 8121 -Name budget -Flags "V1_LIVE_BUDGET=true"
```

`scripts/v1/ab-server.sh <port> <name> [--auto] [KEY=VALUE ...]` is the same for Git Bash and Linux (`OVERRIDES=`
in the environment for auto). Then, from `backend\`:
`python -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out <dir> --target budget=http://127.0.0.1:8121 --target auto=http://127.0.0.1:8120 --runs 5 --loops 8`.

### 3.6 Going back

- One behaviour of auto mode misbehaves: its line in `backend/config/overrides.yaml` (3.2), restart the backend.
- Auto mode as a whole: `V1_MODE=manual` in `backend/.env` and the flags you want (3.3), restart. With no flag set
  that is v0's behaviour.
- The removed features: the last commit that has them is `339589c` (ADR-0037).

## 4. Routing

`backend/config/routing.yaml` lists, per mode (`live`, `studio`, `studio_hq`), engine and step, the providers in
order. A provider whose address or key is not set is skipped. `GET /api/v1/routing` shows what is configured and
what is in use now. Add a model server by starting it and setting its address in `backend/.env`
(`V1_QA_URL`, `V1_TRANSCRIBE_URL`, `V1_BIG_LLM_URL`, `V1_TTS_SERVER_URL`, `V1_MAYA_URL`).

## 5. The GPU's two modes

Normal: v0's servers as they are (about 34 of 40 GB). HQ window: the small translation model on 9020 is stopped
and a larger one runs on 9044 (and Indic Transcribe on 9043) for Studio HQ.

```bash
scripts/v1/gpu-mode.sh hq               # prints what it would do
scripts/v1/gpu-mode.sh hq --run         # refuses while a session is live
scripts/v1/gpu-mode.sh normal --run     # back; starts 9020 with v0's own start script
```

During the window v0 and v1 Live translate through the hosted model by themselves. Run it at night or when nobody
is live. Every switch is written to `<data>/gpu-mode.log`.

HQ jobs for a window: create them with `hold=true` (they wait), open the window, then
`curl -X POST http://127.0.0.1:8110/api/v1/hq/batch -H 'content-type: application/json' -d '{}'`. The batch does
the audio work of every job, then the text work of every job (the big model is used once), then the voices.

## 6. Roll back to v0

v0 was never changed, so rolling back is using v0's address again: website 3000, backend 8010.

- One behaviour misbehaves: switch it off in `backend/config/overrides.yaml` (section 3.2; in manual mode: its flag)
  and restart the v1 backend.
- v1 as a whole misbehaves: `scripts/v1/stop-local.sh` (or `docker compose ... down`). Nothing in v0 depends on v1.
- The code: tag `v0-baseline` (commit `80c36d8`) is v0 as it was before v1.
- The card is stuck in an HQ window: `scripts/v1/gpu-mode.sh normal --run`; if 9020 still does not answer, run
  v0's `start_llm.sh` in its engine folder. Until then v0 translates through the hosted model.

## 7. Backup and restore on a new GPU machine

```bash
V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh --dry    # what would be copied
V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh
```

Copied: the store, voice samples, the trace, the routing and compose files, the names (not the values) of the
settings. Not copied: keys, the cache, uploads and renders. Needs a bucket and a signed-in `gcloud`
(`NEEDS_APPROVAL.md`).

Restore on a fresh machine with an NVIDIA GPU:

1. v0's model servers: v0's engine folder and its `setup_machine.sh`, `setup_gpu_mode.sh` and start scripts
   (models download again from Hugging Face; IndicF5 is gated, sign in first).
2. `git clone` the repository to `/srv/bharatdb-v1/app`, `git checkout v1`.
3. Copy the backup's store and `voices/` into `/srv/bharatdb-v1/data/`; write `backend/.env` from
   `backend/.env.example` (the keys come from wherever they are kept, not from the backup).
4. `scripts/v1/run-local.sh`, then `scripts/v1/demo-check.sh` and `scripts/v1/warmup.sh`.

This restore has not been rehearsed. A VM disk snapshot (taken in the cloud console) is the faster way back and
is the user's to take.

## 8. Deploy kit for the new model servers (v1.1 WS5)

On the GPU machine, in the copied folder (`~/gpu_engine_v1`; the full `ssh` lines are in `NEEDS_APPROVAL.md`):

```bash
bash deploy/status.sh                 # what answers, what the kit started, free GPU memory (read-only)
bash deploy/start.sh qa               # qa | tts | maya | transcribe | big-llm [--size 12b|31b]
bash deploy/start.sh tts --dry-run    # check the card and print every command, start nothing
bash deploy/smoke.sh qa               # PASS/FAIL per check, time, GPU memory held; exit code 0 or 1
bash deploy/stop.sh qa                # only the process in the kit's own pid file
```

| Server | Port | Needs (GB, not measured) | Free must be at least |
|---|---|---|---|
| `qa` | 9045 | 0 (CPU, no CUDA device) | 4 |
| `tts` | 9041 | 4 | 8 |
| `maya` | 9042 | 9.2 | 13.2 |
| `transcribe` | 9043 | 10 | 14 |
| `big-llm` 12B / 31B | 9044 | 14 / 27 | 18 / 31 |

- `start` refuses when free minus need is under 4 GB, when the port already answers, or (for a GPU server) when
  `nvidia-smi` gives no answer. `--need-gb N` replaces the table's figure once it is measured.
- Files: `run/<server>.pid`, `.json`, `.log`; environments in `.venvs/`; models in `~/bharatdb-v1-models`
  (`V1_MODEL_CACHE`). `--python PATH` uses an existing interpreter; `--stub` starts a server without its model.
- Settings read from the environment at start: `QA_DEVICE`, `QA_HEAR`, `QA_THREADS`, `QA_SPK_MODEL`,
  `QA_SPK_ALLOW_NONCOMMERCIAL`, `QA_DIARIZE`, `HF_TOKEN`, `NFE`, `BATCH_MAX`, `MAYA_SEATS`, `MAYA_COMMIT`,
  `BIG_LLM_MODEL`, `BIG_LLM_REVISION`, `BIG_LLM_CTX`, `VLLM_BIN`, `VLLM_VERSION`, the `*_REVISION` pins.
- CUDA MPS and v0's servers (9001-9003, 9010, 9020, 9030, 9040) are never touched by the kit.

The backend alone on the machine: `bash scripts/v1/vm-backend.sh --check`, then without `--check`
(`NEEDS_APPROVAL.md` item 2); stop with `scripts/v1/stop-local.sh`.

A/B kits: `gpu_engine_v1/ab/maya_ab.py --help` (voices) and `python -m eval.v1.llm_ab --help` from `backend/`
(translation; steps `run`, `sheet`, `verdict`).
