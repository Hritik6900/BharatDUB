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
| `V1_LIVE_RECORD` | v1.1 pitch kit: a Live session **that was made with `record: true`** (the tick "Keep a recording of this session's dub" on `/live`, shown only while this flag is on) saves its dubbed sound, one track per language, and its phrase times and captions under `<DATA_DIR>/recordings/<session>/` | off: the tick is not shown, the ask is ignored, nothing is written. Delete the folders to remove what was kept |
| `V1_LISTEN_TEST` | v1.1 pitch kit: `/listen-test` and its routes: blind A/B pairs from `<DATA_DIR>/listen/pairs`, answers in `<DATA_DIR>/listen/results.jsonl`, summary on `/metrics-ui` | off: the routes answer 404, the page says it is off, the summary is not shown |
| `V1_STORE` | `postgres` (with `POSTGRES_DSN`) | `json` |

Not a flag but a setting: `LIVE_FIT_MAX_TEMPO=1.2` caps the Live speed-up at 1.2x (v0: 1.3).

`V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE` no longer exist (removed in v1.1 WS6, `PROGRESS.md`). A line that
still sets one of them in `backend/.env` is ignored: the backend starts as if it were not there.

### Recommended settings for v1's `backend/.env` (v1.1 WS6)

The code's defaults stay off. This is what to write into v1's own env file; a ready block is at the end of the v1
part of `backend/.env.example`. Every number below is from `EVAL_REPORT.md`, `LIVE_DENSE_REPORT.md` or
`PROGRESS.md`; nothing was measured for this list.

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
| `V1_HQ_REVIEW` | **on, with `V1_STUDIO_HQ`** | without it HQ's merge and clean steps damaged the transcript of two of three test videos: 25 of 38 lines no longer the line heard, 0 with it. 24 of 76 lines edited by the reviewer. Words heard back 94.5% against 95.9% without it (the figure cannot see a damaged transcript); its edits were not judged by ear |
| `V1_HQ_JUDGE` | **on, with `V1_STUDIO_HQ`** | the counting rule no longer takes points off Bengali for a letter stored two ways: Bengali +5.6 to 6.3 points on the same output, Tamil unchanged, 25 flags become 15 |
| `V1_BREAKER` and `V1_LIVE_DEGRADE` | **on, both together** (not on the list above: point 3) | all three GPU endpoints stalled for 50 s: flags off (1 run) 4 of 22 phrases translated and dubbed; on (3 runs) 23, 24, 23 of 23, 24, 23, in a stock voice, first audio median 3.1-3.5 s. Healthy calls stayed far under the limits (slowest voice line 1.36 s of 4 s, slowest translation 1.13 s of 3 s). The stall was made with a relay, not a real tunnel |
| `V1_LIVE_BUDGET` | **on where Punjabi-like languages are the target; your call for Tamil** (point 4) | dense reel, Punjabi + Tamil, 5 runs: within 0.25 s 63.5% -> 80.6%, within 1 s 86.5% -> 92.3%, dub length over slot p90 1.42 -> 1.17, lines at 1.3x 46 -> 24 of 185; 15% fewer letters said; in Tamil 7 of 20 lines read had lost something that mattered |
| `V1_LIVE_RATECTRL` | off | with the budget: 83.1% within 0.25 s against 80.6%, 91.8% within 1 s against 92.3%: inside the spread; it brings 1.4x on 15 lines a run, which nobody has heard |
| `V1_LIVE_NATIVE_SPEED` | off | acted on 6.6 lines a run, all Tamil; no number moved |
| `V1_LIVE_WARMSTART` | off (your call) | first audio p95 of the first 10 phrases 4.27 s -> 3.80 s over 5 runs each with the final build, 3.86 s -> 4.79 s with the first build, and "off" alone moved 0.41 s between batches: no proven gain. Its matched stock voice and softened change of voice need ears |
| `V1_EN_SINGLE_VOICE` | on with `V1_EN_VOICE=auto` only if English is a target and one voice matters more than the copied one; else off | English + Punjabi, 3 runs each: stock lines between copied ones 4.7 a session and 9 changes of voice with it off, none with it on. Every English line in the hosted copy: within 1 s 86.6% -> 73.7% |
| `V1_PHRASE_DYNAMIC` | off (your call: point 2) | a session's first audio 5.9 s -> 4.1 s when a voice is ready at the start (stock voices); 5 points fewer phrases on time on dense speech (69.6% -> 64.5%, voice learned from the stream) |
| `V1_LIVE_LATE_SHORTEN` | off | skips 4.7 -> 1.7 a run, measured only inside a bundle whose timing was worse (56.0% on time against 69.6%); its own effect was not separated |
| `V1_LIVE_BACKCHECK` | off | not measurable: no scorer until the QA server runs (`NEEDS_APPROVAL.md` item 6); it does nothing without one |
| `V1_TTS_SERVER`, `V1_TTS_MAYA` | off | as of v1.1 WS4 neither server was loaded; nothing measured |
| `V1_HQ_ADAPTIVE` | off | against v1's own rule the same number of takes (143); it only saves against five fixed takes (206 s against 524 s of voice time) |
| `V1_HQ_NORMALISE` | off until a video with numbers has been heard | nothing to do on the three test videos (no digits); unit tests only |
| `V1_HQ_AUTO_GLOSSARY` | off (your call; harmless) | 16 names and terms proposed over three videos; its effect on the dub was not separated from the review's |
| `V1_HQ_CALIBRATE` | on when someone is going to label; it only adds a page | the page works on real takes; no labels yet, so no agreement figure |
| `V1_LIVE_RECORD` | off | not a speed or quality change; on only for a session whose speaker agreed to a video being made (nothing deletes a recording by itself) |
| `V1_LISTEN_TEST` | off until pairs exist in the data folder | no pairs and no ratings yet |
| `V1_STORE` | `json` | `postgres` was never run against a database |

Not a flag: `LIVE_FIT_MAX_TEMPO` stays at its default (phrases at the limit 20 -> 25 with 1.2; nobody has heard
1.2x against 1.3x).

**Where the reports and the list pull in different directions:**

1. **`V1_STUDIO_HQ` without `V1_HQ_REVIEW`.** The list switches HQ on and not the review. v1.1 WS3 found that HQ
   without it dubbed two of three test videos from a damaged transcript, and that the heard-back figure cannot
   see it. So the ready block switches `V1_HQ_REVIEW` and `V1_HQ_JUDGE` on as well. If they are left off, do not
   offer the HQ choice.
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

The pitch kit (v1.1 WS4; `PROGRESS.md`). **A recorded session.** Live audio is never stored; the one exception
needs two yeses: `V1_LIVE_RECORD=true` on the backend and `record: true` on that session (the console tick; the
replay harness: `--record`). Then `<DATA_DIR>/recordings/<session>/` (or `V1_RECORD_DIR`) holds `session.json`,
`dub_<lang>.wav` (one continuous mono track per language on the session's clock, each phrase where a viewer's
player starts it) and `phrases.jsonl` (per phrase and language: `seq`, `t_speech_ms`, `media_s` = the video's time
it was spoken at, `start_ms` / `track_ms`, `dur_ms`, `late_ms`, `hold_ms`, `first_audio_ms`, `voice` copied or
stock, `tempo`, the caption `text`; or `skipped` and why). The stream's own sound is not kept. The caption text is
in that folder only: not in the trace, not in `logs/`. Nothing deletes a recording by itself.
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
powershell -File scripts\v1\ab-server.ps1 -Port 8120 -Name pitch -Flags "V1_LIVE_RECORD=true"    # its own window
cd backend; .venv\Scripts\python.exe -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\pitch `
    --target rec=http://127.0.0.1:8120 --runs 1 --loops 3 --langs pa-IN --record
# the recording is then in data-v1\ab\pitch\recordings\<session>
```

**The blind listening test.** `V1_LISTEN_TEST=true`, then `/listen-test`. Pairs live in
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
