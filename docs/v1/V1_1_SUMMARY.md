# v1.1 summary (24-25 Nov 2026)

> **After this summary, v1.2 (26 Nov 2026):** v1 runs in auto mode (`V1_MODE=auto`); the flags of section 3
> are read in manual mode only. `V1_LIVE_RATECTRL`, `V1_LIVE_NATIVE_SPEED`, `V1_LIVE_WARMSTART` and
> `V1_PHRASE_DYNAMIC` were removed. **Section 6 is v1.2: what changed, the numbers before and after, and what
> needs you.** Measured there: on dense Live speech auto mode as shipped is worse than the "budget" column of
> section 2.1 (82.4% against 90.0% within 1 s on the same day).

What v1.1 added to v1, what each part measured, which flags to switch on, what waits for you, and the commands.
Every number here is quoted from the report named beside it; nothing was measured for this page. Where a target
was not reached it says so. Detail per workstream: `PROGRESS.md`. Code defaults: every flag off, except
`V1_HQ_ADAPTIVE` (on since 26 Nov 2026, v1.2 Part 1; it acts on HQ jobs only).

Tests: 311 pass, 1 skipped. v0 was not changed.

## 1. What shipped

| Workstream | What | Flags (all default off) | Commit |
|---|---|---|---|
| WS0 Never die | circuit breakers on the GPU endpoints with a link-stall detector; Live ladder copied voice, stock voice, captions only, original sound, and back; status page shows the A100 as unknown until the VM reports it; watcher lines for circuits and rungs; tunnel watchdog script (not run) | `V1_BREAKER`, `V1_LIVE_DEGRADE` | `2cad302` |
| WS1 Dense speech | `dur_ratio` and backlog per phrase; expansion model per language; duration budget for the translator with one shorter re-ask; PI controller on the backlog with a dense mode; engine speed with a pace floor; replay harness | `V1_LIVE_BUDGET`, `V1_LIVE_RATECTRL`, `V1_LIVE_NATIVE_SPEED` | `5ec5f4c`, `ce156a8` |
| WS2 Session start, English | warm start per language, stock voice picked by the speaker's pitch, softened change to the copied voice; one English voice per session | `V1_LIVE_WARMSTART`, `V1_EN_SINGLE_VOICE` (`V1_EN_VOICE=auto\|copy\|stock`) | `0ec4418` |
| WS3 Studio HQ | corrected counting rule of the heard-back judge with a judge order per language; calibration page; adaptive number of takes; number/date/currency normaliser (Hindi, Bengali, Tamil, English); auto-glossary; reviewed translation with a transcript guard | `V1_HQ_JUDGE`, `V1_HQ_CALIBRATE`, `V1_HQ_ADAPTIVE`, `V1_HQ_NORMALISE`, `V1_HQ_AUTO_GLOSSARY`, `V1_HQ_REVIEW` | `93b5e75` |
| WS4 Pitch kit | opt-in recording of a session's dub; side-by-side renderer; blind listening page with a summary on `/metrics-ui` | `V1_LIVE_RECORD`, `V1_LISTEN_TEST` | `bc48922` |
| WS5 GPU upgrades prepared | deploy kit (start, smoke, stop, status; refuses unless free memory minus need is at least 4 GB); Maya 2 voice A/B kit; 12B translation A/B kit with a written rule for "wins"; QA server on CPU with a licence guard on the speaker model; the approval list as one ordered checklist | none | `df27b93` |
| WS6 Cleanup | `V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE` removed with their code; recommended settings written down | two flags removed | `e3128ef` |

## 2. Before and after

### 2.1 Live on dense speech (`LIVE_DENSE_REPORT.md`)

The dense 24.9 s reel played 8 times (211 s, 89% speaking share), Punjabi + Tamil, GPU engine, voice learned from
the stream, sync mode, hold fixed at 6 s, 5 runs a setting, interleaved. Mean (lowest-highest).

| | Flags off | Budget | Budget + controller | + engine speed | Target |
|---|---|---|---|---|---|
| Within 0.25 s of the moment | 63.5% (57.9-68.6) | 80.6% (77.8-83.6) | 83.1% (81.9-84.4) | 82.8% (80.5-85.9) | |
| Within 1 s | 86.5% (84.2-90.6) | 92.3% (89.8-96.1) | 91.8% (89.2-95.3) | 91.5% (87.7-94.7) | 90%: **reached** with the budget |
| `dur_ratio` p50 / p90 | 0.98 / 1.42 | 0.91 / 1.17 | 0.85 / 1.11 | 0.84 / 1.09 | p90 1.0: **not reached** |
| Skips per 10 min | 7.1 (0-17.9) | 7.8 (0-35.8) | 9.5 (0-32.7) | 19.7 (0-44.8) | 1: **not reached** |
| First audio p50 / p95 | 2.41 / 3.92 s | 2.63 / 4.40 s | 2.65 / 4.69 s | 2.62 / 4.75 s | |

What the budget costs: 15-18% fewer letters spoken; about half the lines asked for twice; words heard back
Punjabi 87.7% to 80.1%, Tamil 84.4% to 82.9% (40 lines a cell); of 20 lines read per language (not by a native
speaker) 2 Punjabi and 7 Tamil lost something that mattered. Not measured: a real long recording (none exists),
how 1.4x sounds.

### 2.2 The link falling away (WS0, `PROGRESS.md`)

A 50 s stall of all GPU endpoints, made with a local relay, dense reel, Tamil.

| During the stall | Flags off (1 run) | Breaker + ladder (3 runs) |
|---|---|---|
| Phrases translated and dubbed | 4 of 22 | all, in a stock voice |
| First audio, median | 8.2 s | 3.1-3.5 s |

Copied voice back 5.6 s after the link returned (final build, 1 run). The three stalls of 24 Nov were the laptop
in standby.

### 2.3 Session start (WS2)

First 10 phrases of a session, Punjabi + Tamil, 5 runs each way. **No proven gain.**

| | Off | Warm start (final build) |
|---|---|---|
| First audio p95 | 4.27 s (3.67-5.05) | 3.80 s (3.40-4.34) |
| First audio p50 | 2.90 s | 2.86 s |

Lower in 4 of 5 pairs, ranges overlap, and "off" alone moved 0.41 s between two batches.

### 2.4 English voice mix (WS2)

English + Punjabi, 211 s, 3 runs each. The user's stream of 24 Nov: 100 English lines, 91 copied, 9 stock,
16 changes of voice.

| English lines | Off | On, `copy` | On, `stock` (= `auto`) |
|---|---|---|---|
| Copied / stock, % of spoken | 59.7 / 40.3 | 67.3 / 32.7 | 0 / 100 |
| Changes of voice in a session | 9 (7-11) | 1 | 0 |
| Within 1 s, whole session | 90.9% | 82.4% | 90.6% |

The mix is gone with the flag on. `copy` is 0.73 s later a line. The hosted stock voice was refusing lines that
night (HTTP 502; 42% of English lines silent in `stock`), so the `stock` column's timing is flattered.

### 2.5 Studio HQ with the corrected judge (WS3, `EVAL_REPORT.md` section 6)

Three videos, 76 lines, Tamil + Bengali, one job per video and setup.

| | 23 Nov as reported (old rule) | 23 Nov output, new rule | 25 Nov rerun |
|---|---|---|---|
| Standard, words heard back | 89.2% | 91.1% | 90.6% |
| HQ, words heard back | 92.5% | 95.5% | 95.9% |
| HQ lines flagged, of 76 | 25 | 15 | 15 |
| HQ time a video, mean | 255 s | same jobs | 128 s |

**Target 96%: not reached** (95.9%; all flags with intact transcripts 94.5%). The fault in the judge was the
counting rule (Bengali letters stored two ways were counted as different words), not the model.
**HQ without `V1_HQ_REVIEW` damaged the transcript in two of three videos** (25 of 38 lines; 0 with the review):
heard-back cannot see that.

### 2.6 Time saved by adaptive takes (WS3)

| Voice stage, three videos | Fixed 5 takes | Adaptive |
|---|---|---|
| Time | 524 s | 206 s (61% less) |
| Takes | 380 | 143 |

On the fixed jobs' own takes the adaptive rule keeps the same take on 76 of 76 lines. Against v1's earlier rule
(up to 4 takes until one passes) it saves nothing: both made 143 takes.

### 2.7 Pitch kit (WS4)

One recorded session rendered to prove the chain: `data-v1\pitch\reel25_pa-IN_split.mp4`, 82.1 s, 35.3 MB (not
committed). The listening page has no pairs and no ratings yet.

## 3. Which new flags to switch on, and why

Full list with one line per flag: `RUNBOOK.md`, "Recommended settings"; a ready block is at the end of the v1 part
of `backend/.env.example`.

| Flag | Recommendation | Why |
|---|---|---|
| `V1_BREAKER` + `V1_LIVE_DEGRADE` | on (your call) | 4 of 22 phrases dubbed through a stall without them, all with them |
| `V1_LIVE_BUDGET` | on for Punjabi-like languages; your call for Tamil | within 1 s 86.5% to 92.3%; Tamil lost meaning in 7 of 20 lines read |
| `V1_LIVE_RATECTRL` | removed in v1.2 (was: off) | no gain over the budget alone; nobody has heard 1.4x |
| `V1_LIVE_NATIVE_SPEED` | removed in v1.2 (was: off) | no timing number moved |
| `V1_LIVE_WARMSTART` | removed in v1.2 (was: off) | no proven gain |
| `V1_EN_SINGLE_VOICE` | on once you chose `V1_EN_VOICE` (checklist item 22) | removes the second voice; `copy` costs timing, `stock` is not your voice |
| `V1_HQ_JUDGE` | on whenever `V1_STUDIO_HQ` is on | corrected count |
| `V1_HQ_REVIEW` | nothing to set: since 26 Nov 2026 an HQ job is always reviewed, whatever this flag says (enforced in code, tested) | review is what keeps the transcript intact: 25 of 38 lines damaged without it, 0 with it |
| `V1_HQ_ADAPTIVE` | **on** (decided 26 Nov 2026; also the code's default now) | against five takes of every line 61% less voice time (206 s against 524 s over three videos) with the same take kept on 76 of 76 lines; against v1's earlier rule (up to 4 takes until one passes) the same number of takes (143), so it costs nothing |
| `V1_HQ_NORMALISE`, `V1_HQ_AUTO_GLOSSARY` | off | normaliser changed no line on the test videos (no digits); glossary's effect not separated |
| `V1_HQ_CALIBRATE`, `V1_LISTEN_TEST` | on when you want to label or run a listening test | pages only |
| `V1_LIVE_RECORD` | off; on only for a pitch recording | Live audio is otherwise never stored. A kept recording is deleted by itself after `V1_RECORD_KEEP_DAYS` (30) and can be deleted at any time (list on `/live`, `DELETE /api/v1/recordings/<session>`) |

One thing from the earlier list to look at again: `V1_LIVE_STOCK_DEFAULT=true` means a `/live` session without a
streamer profile never learns a voice, and every v1.1 Live number was measured with a learned voice.

## 4. What waits for you (`NEEDS_APPROVAL.md`, in order)

| # | Item | Kind |
|---|---|---|
| 1-3 | Move the v1 backend to the GPU machine: look at the machine, start the backend there, Docker (optional) | VM |
| 4 | QA server on the machine's CPU (:9045) | VM |
| 5 | The card's real numbers on the status page | VM + laptop |
| 6 | A second judge for Tamil, Bengali and others | VM |
| 7 | Diarization | VM + you |
| 8 | Maya 2 (:9042) and the voice A/B | VM + laptop + you |
| 9 | Big translation model: 12B first, 31B only if 12B wins | VM + laptop + you |
| 10 | Voice server with batching (:9041) | VM |
| 11 | Indic Transcribe (:9043) | VM + you |
| 12 | Pin the model versions | VM |
| 13-15 | Domain and HTTPS, Postgres store, backup bucket | VM (+ you) |
| 16 | Stop the laptop sleeping on AC power | laptop |
| 17 | Tunnel watchdog | laptop |
| 18 | Five comparison backends left on 8111-8115 | laptop |
| 19 | What the session-start measurement could not cover | laptop + you |
| 20 | Two or three dense recordings of about 10 minutes | you |
| 21 | Labels for the calibration page (30 a language, from a speaker of it) | you |
| 22 | Which English voice | you |
| 23 | Prices for the cost per minute | you |
| 24 | The decisions in one place | you |
| 25 | A pitch video of a real stream; how long recordings stay | you + laptop |
| 26 | Listeners for the blind listening test | you |
| 27 | Documentation: the handbook's "(unconfirmed)" items (its `V1_HQ_ADAPTIVE` point was settled on 26 Nov 2026: on) | you |
| 28 | Get written confirmation of commercial use from AI4Bharat / legal review (IndicF5) | you |
| 29 | Auto mode on `/live`: stock voices or the learned voice, the breakers on a link that hiccups, the meaning check's first step (section 6) | you + laptop |

Items 16-18 take five minutes and need no VM. Known before deploying: by the estimates 31B does not fit beside the
voice engines; whether the 12B checkpoint starts on the machine's vLLM is not known; the deploy kit has not run on
Linux. Other documents written before 25 Nov cite old item numbers; the table at the end of the checklist
translates them.

## 5. Commands (PowerShell, from `C:\Users\hriti\Desktop\BharatDUB-v1`)

```powershell
# v1: backend 8110, website 3100
powershell -File scripts\v1\run-local.ps1

# replay harness: two comparison backends in their own windows, then the runs (check no stream is live first)
powershell -File scripts\v1\ab-server.ps1 -Port 8120 -Name off
powershell -File scripts\v1\ab-server.ps1 -Port 8121 -Name budget -Flags "V1_LIVE_BUDGET=true"
cd backend; .venv\Scripts\python.exe -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\replay `
    --target off=http://127.0.0.1:8120 --target budget=http://127.0.0.1:8121 --runs 5

# calibration page: V1_HQ_CALIBRATE=true and V1_HQ_JUDGE=true in backend\.env, restart, then open
#   http://localhost:3100/studio/calibrate

# listen test: build pairs, V1_LISTEN_TEST=true in backend\.env, restart, then http://localhost:3100/listen-test
backend\.venv\Scripts\python.exe scripts\v1\make-listen-pairs.py C:\clips\indicf5 C:\clips\other `
    --system-a indicf5 --system-b other --lang ta-IN --name "what this set is"

# pitch renderer: record one session (V1_LIVE_RECORD=true and the tick on /live, or the harness with --record)
powershell -File scripts\v1\render-pitch.ps1 -Recording data-v1\recordings\<session> -Video C:\path\video.mp4 `
    -Lang pa-IN -Stereo split -Out data-v1\pitch\<name>.mp4
```

The stream watcher window must be restarted to show the new lines (`powershell -File scripts\v1\stream-watch.ps1 -Window`).

## 6. v1.2 (26 Nov 2026): what changed, before and after, what needs you

Detail: `PROGRESS.md` "v1.2 Part 1", "v1.2 Part 2", "v1.2 Parts 3-4". Every number below was measured on 26 Nov
2026 unless a date is given. Tests: 348 pass, 1 skipped. v0 was not changed. **The backend on 8110 and the website
on 3100 still run the code they were started with**; the commands to switch them are at the end.

### 6.1 What changed

| Part | What |
|---|---|
| 1. Your six decisions | `V1_HQ_ADAPTIVE` on everywhere; HQ never runs without the review (in code, tested); kept Live recordings are opt-in, deleted after 30 days, listed and deletable one by one; the viewer hold eases back to 6 s after a slow link; Demucs, Silero VAD and IndicF5 licences recorded (IndicF5: legal confirmation needed, item 28); the 67-minute stream leads `PITCH_FACTS.md` |
| 2. Auto mode | `V1_MODE=auto` is the default: one function decides what is in force, one file (`backend/config/overrides.yaml`) switches a single behaviour off, no page shows a switch. Always on: trace, router, API log, breakers and ladder, stock voices on `/live`, Studio HQ with review, 1.15x fit, adaptive takes, normaliser, job glossary, HQ judge. Auto budget (only while behind or dense), a meaning check on a sample that loosens a language's budget, the English voice chosen once from a timed probe, a refused line spoken by another voice and never silent without a record, a script guard and a content-shift check. Removed with their code: `V1_PHRASE_DYNAMIC`, `V1_LIVE_NATIVE_SPEED`, `V1_LIVE_WARMSTART`, the switch `V1_LIVE_RATECTRL` |
| 3. Measured | auto against "budget on" on the dense reel, 5 runs each in turn, with two more auto settings to tell the causes apart; Studio HQ in auto mode on the three videos. One bug fixed on the way (the log collector dropped index rows) |

### 6.2 Live on the dense reel: auto against "budget on"

The reel played 8 times, Punjabi + Tamil, GPU engine, hold fixed at 6 s, 5 runs a setting taken in turn, one
session at a time, nobody live on v0 or v1. Mean (lowest-highest). The first two columns are v1.1's runs of 24
Nov for reference (another day).

| | Flags off (24 Nov) | Budget (24 Nov) | **Budget on, manual mode** | **Auto, as shipped** | Auto + `live_stock_default: off` | ... + `breaker: off`, `live_degrade: off` |
|---|---|---|---|---|---|---|
| Within 0.25 s | 63.5% (57.9-68.6) | 80.6% (77.8-83.6) | **79.1% (73.2-81.8)** | **66.3% (57.4-75.1)** | 69.6% (55.7-80.8) | 74.2% (72.4-76.6) |
| Within 1 s | 86.5% (84.2-90.6) | 92.3% (89.8-96.1) | **90.0% (87.4-94.0)** | **82.4% (71.0-89.3)** | 83.9% (72.1-90.9) | 88.5% (86.4-90.1) |
| dur_ratio p90 | 1.42 | 1.17 | 1.16 (1.13-1.19) | 1.20 (1.17-1.22) | 1.15 (1.04-1.26) | 1.16 (1.09-1.24) |
| Skips per 10 min | 7.1 (0-17.9) | 7.8 (0-35.8) | 3.0 (0-6.1) | 34.1 (0-113.8) | 22.1 (3.0-86.6) | 5.4 (0-11.9) |
| First audio p50 / p95 | 2.41 / 3.92 s | 2.63 / 4.40 s | 2.68 / 4.94 s | 2.98 / 5.69 s | 2.97 / 5.38 s | 2.77 / 4.69 s |
| Lines in the copied voice | 97.4% | 96.1% | 95.1% | 0% (stock voices) | 83.1% (50.9-97.3) | 97.0% |
| Unspoken lines / silent without a mark | not recorded | not recorded | not marked in manual mode / 0 | 1 in 5 runs / 0 | 0 / 0 | 0 / 0 |
| Script guard: failed / flagged, a run | - | - | not run | 7.2 / 5.8 | 5.0 / 5.0 | 3.2 / 3.2 |
| Meaning sample: judged as lost (model judge) | - | - | not run | 23.3% (14.3-26.7) | 19.0% (15.0-25.9) | 14.8% (6.8-20.0) |
| Budget loosened, steps a run | - | - | - | 3.2 (2-4) | 2.4 (2-4) | 1.6 (0-2) |
| Share of lines under the budget | none | all | all | 93.0% | 94.1% | 96.2% |
| Words heard back, corrected rule (40 lines a cell): Punjabi / Tamil | not re-counted | not re-counted | 91.3% / 86.3% | 86.4% / 83.5% | 88.9% / 83.8% | 87.0% / 87.1% |
| Meaning read on 20 lines, lost or wrong: Punjabi / Tamil | - | 2 / 7 (budget + controller) | 4 / 7 | 9 / 6 | 4 / 10 | 3 / 10 |

- Two pure-auto runs had a stall of the laptop's connection and were repeated: with them replaced auto is 66.8%
  (57.4-81.9) and 82.1% (71.0-92.3). Pure auto's seven runs go from 38 skipped lines to 1.
- The meaning read is by the author of the report, not a native speaker (the same reader and rule as v1.1's "7 of
  20"); the judge of the meaning sample is a language model.
- Words heard back as v1.1 counted it (for the 24 Nov columns: flags off 87.7% / 84.4%, budget + controller 80.1%
  / 82.9%): budget on 86.2% / 85.3%, auto 82.7% / 79.7%, learned voice 84.0% / 83.3%, no breaker 83.1% / 83.1%.

### 6.3 Where auto is worse, and why

| Measure | Auto as shipped | Best earlier setting | Why (evidence in EXP-031) |
|---|---|---|---|
| Within 0.25 s | 66.3% (57.4-75.1) | 79.1% manual budget (80.6% on 24 Nov; 83.1% budget + controller, since removed) | stock voices on `/live`: every line waits for the hosted account's one request. A stock line started within 1 s 48-83% of the time, a copied line 87-91%; the wait for the voice was p90 2.1 s and p95 3.6 s against 1.2-1.5 s and 1.5-1.9 s |
| Within 1 s | 82.4% (71.0-89.3) | 90.0% manual budget (92.3% on 24 Nov) | the same; and it swings with the hosted voice's speed: one long line took 1.1 to 7.3 s over the afternoon |
| Skips per 10 min | 34.1 (0-113.8) | 3.0 manual budget | the same queue: 38 skipped in the slow hour, 0-2 in four other runs; 14 and 4 in the two runs with a stalled connection |
| First audio p50 / p95 | 2.98 / 5.69 s | 2.68 / 4.94 s (2.41 / 3.92 s flags off, 24 Nov) | the wait for the voice's turn |
| Copied voice | 0% | 95-97% | `LIVE_STOCK_DEFAULT` always on: your list |
| dur_ratio p90 | 1.20 | 1.16 manual budget (1.11 budget + controller at 1.4x, 24 Nov) | the stock voice is slower in Punjabi (p90 1.24 against 1.11) and the meaning check loosens the budget |
| Meaning, Punjabi, 20 lines read | 9 lost or wrong | 4 manual budget | the budget cuts harder for a slower voice: 2.51 target letters a source word against 3.03 |
| Meaning, Tamil, 20 lines read | 6 (10 with the learned voice) | 7 manual budget | auto's budget while dense is at most 0.9 of the slot with the controller on top; in the lines read Tamil was at loosening step 0 or 1 in the two settings with the learned voice |
| With the learned voice: copied voice 83.1% (50.9-97.3), within 1 s 83.9% | | 95.1%, 90.0% | the breakers: a health answer over 2 s or a line over 4 s takes the copied voice away for about 34 s (13 times in 3 of 5 runs; the engine itself never over 0.62 s) and the stock voice then queues |
| With the learned voice and no breaker: within 0.25 s 74.2% | | 79.1% | the meaning check loosened a language in 4 of 5 runs; a loosened language has more lines longer than their slots (Punjabi 40-45% against 16%, Tamil 29-46% against 25%) |
| Studio HQ time a video | 146 / 152 / 160 s | 133 / 117 / 136 s HQ, 140 / 129 / 130 s HQ + flags (25 Nov) | the content-shift judge on every line (about 6 s) and more takes (178 against 143-156); one job each, another day |

Where auto is **not** worse: Studio words heard back (95.6% against 95.9% with two damaged transcripts and 94.5%
with intact ones; auto's are intact), lines without sound (none unrecorded), and with the learned voice and no
breaker it overlaps "budget on" within 1 s (88.5% against 90.0%).

### 6.4 Studio HQ on the three videos

One job a video, Tamil + Bengali, nothing cached. The v1.1 columns are the jobs of 25 Nov: not interleaved.

| | Standard (25 Nov) | HQ (25 Nov) | HQ + all flags (25 Nov) | **HQ, auto mode** |
|---|---|---|---|---|
| Words heard back (corrected rule) | 90.6% (88.4-93.0) | 95.9% (93.3-98.1) | 94.5% (93.2-96.5) | **95.6% (94.6-96.5)** |
| Total time, A / B / C | 81 / 54 / 66 s | 133 / 117 / 136 s | 140 / 129 / 130 s | 146 / 152 / 160 s |
| Voice stage, A / B / C | 23 / 24 / 25 s | 73 / 67 / 79 s | 77 / 73 / 75 s | 74 / 93 / 92 s |
| Takes / lines flagged, of 76 | 76 / none scored | 143 / 15 | 156 / 21 | 178 / 20 |
| Damaged transcript lines, A / B / C | - | 0 / 13 / 12 | 0 / 0 / 0 | 0 / 0 / 0 |
| Script guard: checked / failed / flagged | - | - | - | 76 / 0 / 0 |
| Content shift: checked / failed / translated again / flagged / not checked | - | - | - | 76 / 0 / 0 / 0 / 0 |
| Unspoken lines | - | - | - | 0 |

All 20 flagged lines are flagged by the heard-back judge (the best of five takes at 67-89%); none by a guard.
**Target 96%: not reached.**

### 6.5 The hold after a slow link (v1.2 Part 1, EXP-030)

A link made 0.7 s slower each way for 70 s, dense reel, Tamil, 2 runs each way.

| | Before (`LIVE_SYNC_EASE=false`) | After (default) |
|---|---|---|
| Highest hold | 11.0 s, 11.0 s | 10.75 s, 11.0 s |
| Hold when the run ended | 11.0 s (180 s after the link was back), 11.0 s (281 s after) | 6.25 s (171 s after), 6.0 s (reached 217 s after) |
| First step down | never | 22.3 s, 23.5 s after the link was back, then 250 ms at a time |
| Within 1 s, phrases after the link was back | 97.6%, 95.3% | 96.4%, 95.5% |
| Within 0.25 s, the same phrases | 67.1%, 70.1% | 65.5%, 57.9% |

The viewer page's part (it plays at 1.1x until it has caught up) was not run in a browser.

### 6.6 What needs you (`NEEDS_APPROVAL.md`)

New in v1.2: **item 29** (auto mode on `/live`: three choices, a line in a file each) and **item 28** (IndicF5:
written confirmation of commercial use). Item 25 keeps one open half (what happens to recordings when a voice
profile is deleted). The rest of section 4 stands.

### 6.7 Switching the running v1 to this code

The build did not restart 8110 or 3100. In PowerShell, from `C:\Users\hriti\Desktop\BharatDUB-v1`, with no
stream live:

```powershell
# 1. see what holds the two ports (the command lines must be v1's uvicorn on 8110 and next on 3100)
Get-NetTCPConnection -LocalPort 8110,3100 -State Listen | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" } | Select-Object ProcessId, CommandLine
# 2. stop those two processes
Get-NetTCPConnection -LocalPort 8110,3100 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess }
# 3. start the backend and rebuild and start the website (auto mode is the default; nothing to set)
powershell -File scripts\v1\run-local.ps1 -Build
# 4. check (in another window)
curl.exe -s http://127.0.0.1:8110/api/v1/flags
```

`"V1_MODE":"auto"` and `"overrides":{}` in the answer mean auto mode as shipped. To choose differently first, see
item 29.
