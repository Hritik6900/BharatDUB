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
circuit breakers, flags that are on) and `/metrics-ui` (numbers from the
trace). Endpoints: `GET /api/v1/health`, `/api/v1/flags`, `/api/v1/routing`, `/api/v1/metrics/summary?hours=24`,
`/metrics` (Prometheus), `POST /api/v1/warmup`.

**When everything stops answering at once:** look at `data-v1/streamwatch/events.log`. `LINK STALL` with the hosted
services in the list means this PC was away (asleep), not the tunnel: all three stalls of 24 Nov 2026 were the
laptop in standby (`NEEDS_APPROVAL.md` item 17). `scripts\v1\tunnel-watchdog.ps1` (item 16) tells a sleeping PC, a
dead tunnel, a stuck ssh and a dead server on the GPU machine apart.

**Before a demo:** 15 minutes ahead run `demo-check.sh` and `warmup.sh`; the card must be in normal mode (not an HQ
window) and no other session live. One GPU through one address is one stream.

## 3. Flags

All in v1's `backend/.env`, all off by default; with every flag off v1 behaves as v0. Restart the backend after a
change. What each one does, and what was measured, is in `PROGRESS.md` and `EVAL_REPORT.md`.

| Flag | On | Roll back |
|---|---|---|
| `V1_TRACE` | a record per Live phrase and Studio line; `/metrics-ui` fills | off: only logging stops |
| `V1_ROUTER` | providers from `backend/config/routing.yaml` | off: v0's fixed table |
| `V1_PHRASE_DYNAMIC` | first phrase 4-6 words, later 8-12, lines under 3 words join the next | off: 6-12 words |
| `V1_SPEC_TRANSLATE` | a paused speaker's words are translated ahead of the final | off |
| `V1_LLM_PREFIX_CACHE` | our translation model: fixed rules first, temperature 0.1 | off |
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
| `V1_LIVE_RATECTRL` | v1.1: a PI controller on the dub's backlog scales that budget (1.0 down to 0.6, back within seconds); when the speaker talks more than 70% of the last 30 s ("dense"): budget at most 0.9 of the slot, lines under 3 words join the next, speed-up up to 1.4x. Needs `V1_LIVE_BUDGET` to have an effect on the translation | off |
| `V1_LIVE_NATIVE_SPEED` | v1.1: our voice engine is asked to speak a line that must be shorter up to 1.2x faster itself, never under 320 ms a word; the rest by tempo as before | off: tempo only |
| `V1_LIVE_WARMSTART` | v1.1 session start: one tiny translation per target language, our voice engines asked for their state (and one short line per language on every engine process when a streamer's stored voice is on them), one tiny hosted line per language the hosted voice will open in; a streamer's stored voice is sent to the engines when the session is created; a stock voice is chosen once per language by the speaker's pitch (male or female, where the language has both) and kept; the change to the copied voice is softened (fade out, fade in, level) | off: v0's warm-up (one translation, first language) and the usual stock voices |
| `V1_EN_SINGLE_VOICE` | v1.1: English in a GPU-engine session is spoken in one voice for the whole session (`V1_EN_VOICE`), never chosen line by line | off: the hosted copy when 2 s are spare, else a stock voice |
| `V1_HQ_JUDGE` | v1.1 Studio HQ: a dubbed line is heard back by the best speech-to-text for its language (hosted first, then our GPU Whisper where it hears the language, which is Hindi only, then the QA server's Whisper once it runs), the next one when the first fails; the comparison treats the two ways of storing one letter as one spelling; every take, line and trace record says who judged it | off: the `score` list of the routing file and v1's comparison |
| `V1_HQ_CALIBRATE` | `/studio/calibrate` and its routes: label takes blind, agreement with the judge, a recommended flag line (`CALIBRATION.md`) | off: the routes answer 404, the page says it is off |
| `V1_HQ_ADAPTIVE` | one take of a line first; more, up to `V1_HQ_ADAPTIVE_MAX` (5), only while the best score is under `V1_HQ_ADAPTIVE_MIN` (0 = the flag line) | off: up to `V1_HQ_NBEST` (4) until a take passes |
| `V1_HQ_NORMALISE` | numbers, decimals, dates, clock times, the rupee and dollar sign, %, units and short forms are written out by rule in Hindi, Bengali, Tamil and English before the voice sees the line; abbreviations in capitals letter by letter for our own voice | off: the model-written step alone, as v1 |
| `V1_HQ_AUTO_GLOSSARY` | names, brands and repeated English terms found in a job's transcript are used as that job's glossary (never saved to the shared one); `GET /api/v1/jobs/<id>/glossary-candidates` | off |
| `V1_HQ_REVIEW` | the hosted model reviews every translated line against the written rubric (meaning, numbers and names, spoken register, fits the slot) and may edit; a cleaned transcript line that changed script or lost its English terms is put back | off: v1's plain review |
| `V1_STORE` | `postgres` (with `POSTGRES_DSN`) | `json` |

Not a flag but a setting: `LIVE_FIT_MAX_TEMPO=1.2` caps the Live speed-up at 1.2x (v0: 1.3).

The two reliability flags belong together (measured together, `PROGRESS.md` v1.1 WS0). Their limits are settings:
`V1_BREAKER_TRANSLATE_TIMEOUT_S=3` and `V1_BREAKER_VOICE_TIMEOUT_S=4` (the whole time one live call may take on our
GPU before the next provider is asked), `V1_BREAKER_OPEN_S=30`, `V1_BREAKER_FAILS=2`, `V1_BREAKER_WINDOW_S=10`,
`V1_LINK_PROBE_EVERY_S=5`. `GET /api/v1/circuits` and the status page show every circuit; the stream watcher prints
`CIRCUIT OPEN / CLOSED / LINK STALL / LINK BACK` and `RUNG` lines.

The session-start and English-voice flags (v1.1 WS2; measured in `PROGRESS.md`): `V1_EN_VOICE=auto` (`auto` is
the measured choice, today the one stock voice; `copy` = the hosted copy for every English line once the session
has it; `stock`), `V1_EN_COPY_LEAD_MS=3500`, `V1_WARM_FADE_MS=150`, `V1_WARM_LEVEL_LINES=2`. A session's
`GET /api/live/sessions/<id>/metrics` shows `warm` (what each warm-up call took, the speaker's pitch, the stock
voice chosen per language and why) and `en_voice`. On a night when the hosted stock voice refuses lines (HTTP 502,
"technical difficulties"), `V1_EN_VOICE=copy` keeps English audible: the hosted copy answered every line then.

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
`V1_DENSE_MAX_TEMPO=1.4`, `V1_DENSE_MERGE_UNDER_WORDS=3`, `V1_NATIVE_MAX=1.2`, `V1_NATIVE_FLOOR_MS=320`.
With the trace or one of these flags on, every Live phrase stores `dur_ratio` (dubbed seconds over the seconds of
its source slot) and `backlog` (how far the dub queue was behind the video); `/metrics-ui`, the session's
`/metrics` and the stream watcher's summaries show them. The model behind the budget starts from
`backend/config/live_expansion.json` (rebuild: `python -m eval.v1.expansion_seed`) and learns from every line.
Replay a recording through Live without YouTube, several settings in turn:
`python -m eval.live_replay <file> --out <dir> --target off=http://127.0.0.1:8111 --target on=http://127.0.0.1:8112 --runs 5`
(on Windows start the comparison backends with `scripts\v1\ab-server.ps1`).

To compare a flag on and off on the same machine, start a second backend on another port with only that flag:
`scripts/v1/ab-server.sh 8112 dynamic V1_PHRASE_DYNAMIC=true`, then
`python -m eval.v1.live <video> --out <dir> --target base=http://127.0.0.1:8111 --target dynamic=http://127.0.0.1:8112`.

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

- One behaviour misbehaves: switch its flag off and restart the v1 backend.
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
