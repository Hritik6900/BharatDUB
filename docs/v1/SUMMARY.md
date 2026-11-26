# v1 summary

23 Nov 2026. Branch `v1`, built in a second checkout on the dev laptop beside v0 (`main`, tag `v0-baseline` at
`80c36d8`). v0's folder, its servers and its data were not changed; v0 was checked after every phase through its
health endpoints and the shared GPU servers' own, and answered every time.

## 1. What is built

| Area | What | State |
|---|---|---|
| Side by side | own ports (website 3100, backend 8110), own data folder, own env file, every new behaviour behind a flag that is off by default | ran on the laptop against the shared GPU servers |
| Status | `GET /api/v1/health`, page `/health`: green or red per service, flags that are on | works |
| Trace and numbers | a record per Live phrase and Studio line (JSONL, Prometheus), `/metrics-ui`, cost per minute for the rates that are set | works; no rate is set, so no cost is shown |
| Router | provider order, timeouts and fallbacks per step from `backend/config/routing.yaml` | works; the shipped file builds the same providers as v0 |
| Live changes | dynamic phrase sizes, short-line merge, translation ahead, late-line shortening, back-check, session glossary, stock default, fixed-rules-first prompt | built, each behind a flag; measured (section 2) |
| Studio HQ | two hearings merged, cleaned transcript, translation with a word limit per line, review, numbers as words, takes scored and the best kept, flagged lines, sidechain ducking, loudness, jobs phase by phase; an editor with every take and a one-click swap | works end to end on real jobs with the models that are loaded |
| Studio HQ, v1.1 WS3 | the judge per language with a corrected counting rule, old jobs scored again without making a voice line, a calibration page (`/studio/calibrate`), adaptive takes, a rule-based normaliser for four languages, glossary candidates from the transcript, a rubric review by the hosted model with every edit logged, a guard on the transcript | built, each behind a flag; measured on three videos (section 2) |
| Pitch kit, v1.1 WS4 | a Live session's dub kept on disk when the session asks for it (`V1_LIVE_RECORD`), a side-by-side video from it (`scripts/v1/render-pitch.ps1`: original beside dubbed, captions, that recording's own numbers), a blind A/B listening page `/listen-test` with its summary on `/metrics-ui` (`V1_LISTEN_TEST`) | built; one example rendered from the test reel (82 s); the listening page has no pairs yet |
| New model servers | batching voice server, Maya 2, Indic Transcribe, QA, big translation model: code, containers, stub mode | stubs tested; **no real model loaded** (GPU memory, licences) |
| Eval | Live comparison across backends, Studio standard against HQ, key words on the hard set, one script for all | works; `EVAL_REPORT.md` |
| Operations | demo check, warm-up, backup, GPU mode switch, runbook | demo check and warm-up ran; backup and mode switch not run |
| Tests | 61 new tests; 159 pass in all, 1 skipped (Postgres store: no database here). After v1.1 WS3: 275 pass, 1 skipped. After v1.1 WS4: 292 pass, 1 skipped. After v1.1 WS6 (two flags and their tests removed): 287 pass, 1 skipped | |

Not as the build notes described, and why:

- **Built on the laptop, not on the VM.** Everything that needs a shell on the VM is in `NEEDS_APPROVAL.md`.
  First audio through the laptop-to-VM link is about 0.5 s slower than it would be on the VM.
- **No new model on the GPU.** About 6 GB is free beside v0 and 4 GB must stay free.
- **No test session on v0.** Running one on port 8010 was refused, rightly: "v0" in the measurements is v1 with
  every flag off, which builds the same providers and runs the same pipeline code.
- **The GPU mode script was not run, not even as a dry run:** its `hq` and `normal` commands are on the list of
  commands not to run. It was syntax-checked and its read-only `status` ran.
- **The ignore rules for the assistant's files are written as patterns**, so the ignore file itself does not spell
  the names; the commit hooks are installed for this checkout only, so v0's commits are untouched.
- **Four flags beyond the first list:** `V1_ROUTER`, `V1_LIVE_LATE_SHORTEN`, `V1_LIVE_BACKCHECK`,
  `V1_LLM_PREFIX_CACHE` (the last one removed again in v1.1 WS6, with `V1_SPEC_TRANSLATE`).

## 2. Flags: what the measurements say

Numbers are from `EVAL_REPORT.md` (three runs per Live setup, one run per Studio video on three videos).

| Flag | Measured | Recommendation |
|---|---|---|
| `V1_TRACE` | on in every run; no error from it | **on** |
| `V1_ROUTER` | same providers as with it off; first audio 2.4 s against 2.3-2.7 s | **on** (needed for the HQ path's provider lists to be changed in one file) |
| `V1_STUDIO_HQ` | words heard back 92.5% (91.1-93.5) against 89.2% (84.9-93.4) for standard; about 3 times the time (255 s against 82 s for a 50 s video); a third of the lines flagged. **Corrected by v1.1 WS3: by the fixed counting rule the same output is 95.5% against 91.1%; rerun 25 Nov: 95.9% against 90.6%, 128 s against 67 s** | **on** as a choice per job, **together with `V1_HQ_JUDGE` and `V1_HQ_REVIEW`**: without the second, two of three test videos were dubbed from a damaged transcript. Under the 96% target |
| `V1_FIT_115` | on in the HQ runs: largest speed-up 1.15x; the test videos hardly needed speeding up | on with HQ; its effect on videos that need more speed-up is covered by tests only |
| `V1_PHRASE_DYNAMIC` | session's first audio 1.7 s earlier when a voice is ready at the start (5.9 -> 4.1 s, stock voices); no gain with a voice learned from the stream; 5 points fewer phrases on time on dense speech (69.6% -> 64.5%) | **your call**: worth it for a streamer's opening line, costs timing afterwards |
| `V1_LIVE_LATE_SHORTEN` | 1-3 lines a run said shorter, skips 4.7 -> 1.7 a run | **your call**: fewer lost lines; measured only inside a bundle whose timing was worse |
| `LIVE_FIT_MAX_TEMPO=1.2` | phrases at the limit 20 -> 25 | off until someone hears 1.2x against 1.3x |
| `V1_SPEC_TRANSLATE` | 0 early translations used in 5 runs | **removed** in v1.1 WS6 |
| `V1_LLM_PREFIX_CACHE` | cache share 61.4% both ways; no faster | **removed** in v1.1 WS6 (the server's cache was already on) |
| `V1_LIVE_BACKCHECK` | not measurable without the QA server | off until the QA server runs |
| `V1_LIVE_STOCK_DEFAULT` | a product rule, not a speed change | **your call** |
| `V1_TTS_SERVER`, `V1_TTS_MAYA` | servers not loaded | off |
| `V1_STORE=postgres` | never run against a database | `json` |
| `V1_LIVE_BUDGET` (v1.1) | dense reel, Punjabi + Tamil, 5 runs: within 0.25 s 63.5% -> 80.6%, within 1 s 86.5% -> 92.3%, dub length / slot p90 1.42 -> 1.17, lines at 1.3x 46 -> 24 of 185; 15% fewer letters said; `LIVE_DENSE_REPORT.md` | **on** for Punjabi and languages like it; **your call** for Tamil (7 of 20 lines read had lost something that mattered) |
| `V1_LIVE_RATECTRL` (v1.1) | with the budget: within 0.25 s 83.1%, within 1 s 91.8%, p90 1.11; inside the spread against the budget alone; 15 lines a run at 1.4x | off until someone has heard 1.4x |
| `V1_LIVE_NATIVE_SPEED` (v1.1) | acts on 6.6 lines a run, all Tamil; no number moved | **off** |
| `V1_LIVE_WARMSTART` (v1.1) | first 10 phrases of a session, Punjabi + Tamil, 5 runs each way: first audio p95 4.27 s -> 3.80 s (lower in 4 of 5 pairs) with the final build, 3.86 s -> 4.79 s with the first build; "off" alone moved 0.41 s between the two batches; the median did not move; 4-6 of 20 lines in a stock voice either way. Nothing was cold on this setup. The matched stock voice was only measured on a female speaker (the voices v0 uses anyway) | **your call**: no proven gain in speed; its other parts (male stock voice for a male speaker, the softened change of voice) need ears |
| `V1_HQ_JUDGE` (v1.1 WS3) | the counting rule no longer takes points off Bengali for a letter stored two ways: Bengali +5.6 to 6.3 points on the same HQ output, Tamil unchanged, 25 flags become 15; every line records its judge (the hosted one answered every hearing; the second judge exists for Hindi only and was never needed) | **on** whenever HQ is on |
| `V1_HQ_REVIEW` (v1.1 WS3) | 24 of 76 lines edited by the hosted reviewer (wrong number, misspelt name, changed meaning among them); a cleaned transcript line that is no longer the line heard is put back: 0 such lines against 25 of 38 in the HQ jobs without it. Words heard back 94.5% against 95.9%: lower, and not because the dub is worse as far as the lines read show | **on** whenever HQ is on (it is the only thing that stops the transcript damage): since 26 Nov 2026 the code enforces it, an HQ job is reviewed whatever the flag says; ears needed on its edits |
| `V1_HQ_ADAPTIVE` (v1.1 WS3) | against five takes of every line: 61% less voice time (206 s against 524 s over three videos), and on the same takes the same take kept on all 76 lines. Against v1's own rule: the same number of takes (143) | **on** (decided 26 Nov 2026, and the code's default since): it saves against five fixed takes and costs nothing against v1's earlier rule |
| `V1_HQ_AUTO_GLOSSARY` (v1.1 WS3) | 16 names and terms proposed over three videos; effect on the dub not separated from the review's | **your call**; harmless |
| `V1_HQ_NORMALISE` (v1.1 WS3) | nothing to do on the test videos (no digits); unit tests for Hindi, Bengali, Tamil, English | on for those four languages once a video with numbers has been heard |
| `V1_HQ_CALIBRATE` (v1.1 WS3) | the page works on real takes; **no labels yet**, so no agreement figure and no recommended flag line | **on**, and thirty labels per language from someone who speaks it |
| `V1_EN_SINGLE_VOICE` (v1.1) | English + Punjabi, 3 runs each: stock lines between copied ones 4.7 a session (10.1%) and 9 changes of voice with it off, none with it on. Every line in the hosted copy: within 1 s 86.6% -> 73.7% where the copy existed, first audio 0.73 s later than a stock line. So `auto` takes the one stock voice. The hosted stock voice refused 59% of its lines that night (the copy none) | **on** with `auto` if one voice matters more than the speaker's voice in English; `V1_EN_VOICE=copy` when the stock voice is failing or the copied voice matters more than timing |
| `V1_LIVE_RECORD` (v1.1 WS4) | not a speed or quality change. One session recorded and rendered: 35 lines, the picture's numbers equal the trace's (91.4% within 0.25 s, 97.1% within 1 s, first audio 2.3 s). With it off, or without the session's own ask, nothing is written (tested) | **off**, and on only for a session whose speaker agreed to a video being made. Since 26 Nov 2026 a recording is deleted by itself after `V1_RECORD_KEEP_DAYS` (30) days and can be deleted at any time (`/live`, `DELETE /api/v1/recordings/<session>`) |
| `V1_LISTEN_TEST` (v1.1 WS4) | no ratings yet: no pairs exist | **on** once WS5's pairs are in the data folder and listeners are asked |

### Recommended `.env` for v1 (v1.1 WS6)

Nothing new was measured for this; the reasons flag by flag, with their numbers, are in `RUNBOOK.md` section 3,
and a ready block is in `backend/.env.example`. The code's defaults stay off.

- **On, as asked:** `V1_TRACE`, `V1_ROUTER`, `V1_API_LOG`, `V1_STUDIO_HQ`, `V1_FIT_115`, `V1_LIVE_STOCK_DEFAULT`.
- **On as well, because a report says the list is not safe without them:** `V1_HQ_REVIEW` and `V1_HQ_JUDGE`
  (HQ without the review dubbed two of three test videos from a damaged transcript: 25 of 38 lines against 0).
  Since 26 Nov 2026 the review is enforced in code for every HQ job; only `V1_HQ_JUDGE` is left to set.
- **On (decided 26 Nov 2026):** `V1_HQ_ADAPTIVE`: against five takes of every line 61% less voice time (206 s against 524 s over three videos) with the same take kept on 76 of 76 lines; against v1's earlier rule (up to 4 takes until one passes) the same number of takes (143), so it costs nothing. It is the code's default now.
- **A report argues for them, they are not on the list, your call:** `V1_BREAKER` + `V1_LIVE_DEGRADE` (through a
  50 s stall 4 of 22 phrases dubbed with them off, all of 23-24 with them on); `V1_LIVE_BUDGET` for Punjabi-like
  languages (within 1 s 86.5% -> 92.3%), which is one switch for every language and costs Tamil content.
- **Off:** `V1_LIVE_RATECTRL`, `V1_LIVE_NATIVE_SPEED`, `V1_LIVE_WARMSTART`, `V1_PHRASE_DYNAMIC`,
  `V1_LIVE_LATE_SHORTEN`, `V1_LIVE_BACKCHECK`, `V1_TTS_SERVER`, `V1_TTS_MAYA`,
  `V1_HQ_NORMALISE`, `V1_HQ_AUTO_GLOSSARY`, `V1_LIVE_RECORD`, `V1_LISTEN_TEST` (until pairs exist),
  `V1_EN_SINGLE_VOICE` (on with `auto` only where English is a target), `V1_HQ_CALIBRATE` (on when someone labels).
- **The list and the reports disagree in one more place:** with `V1_LIVE_STOCK_DEFAULT` on, a `/live` session
  without a streamer profile never learns a voice, and every v1.1 Live number was measured with a learned voice.
  The only v1 runs in stock voices had first audio p50 5.1 s and 58.3% within 1 s, against 2.34 s and 83.3% with
  the learned voice on the same reel.
- **Removed:** `V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE` (no gain measured; the commit before v1.1 WS6 has them).

Against the targets: Studio words heard back 92.5% (target 96%): not reached (v1.1 WS3: 95.9% by the corrected
rule in a rerun, still not reached, and the figure does not see a damaged transcript; `EVAL_REPORT.md` section 6). Live first audio 2.3-2.5 s through
the link (target 1.8 s) and on time 56-70% (target 90%): not reached, and no Live flag moves either. Hard-audio
key words: hosted 71.3 of 80 (target 73), our Whisper 52. "Warm and green five minutes after a VM restart": not
tested.

What would move the Live numbers, by what was measured before and here: the backend on the GPU machine (v0
measured 1.8 s first audio there; `NEEDS_APPROVAL.md` item 3), not these flags.

## 3. Waiting for approval (`NEEDS_APPROVAL.md`, with exact commands, expected GPU memory and rollback)

| # | What | Needs |
|---|---|---|
| 1 | Find v0's processes and paths on the VM, GPU memory per process | a shell on the VM (read-only commands) |
| 2 | Docker on the VM | `sudo`, system packages |
| 3 | Put v1 on the VM | a shell on the VM, `/srv/bharatdb-v1` |
| 4 | Domain, HTTPS, demo password | DNS, firewall |
| 5 | Postgres store | a database to test against |
| 6 | QA server on CPU (back-check without the hosted account, speaker similarity) | a shell on the VM; no GPU memory |
| 7 | Batching voice server (:9041) | 8 GB free on the card; a comparison with v0's audio |
| 8 | Indic Transcribe (:9043) | an HQ window; its licence decision; accepting its terms |
| 9 | Big translation model (:9044) and the HQ window | stopping v0's small model for a while; which size; vLLM tag |
| 10 | Maya 2 (:9042) | an HQ window; keep-or-drop by ear |
| 11 | Diarization | accepting pyannote's terms, a token |
| 12 | Model versions to pin | the full commit hashes at first download |
| 13 | Backup bucket; VM snapshot; restore rehearsal | the cloud console |
| 14 | Prices for the cost per minute | the real rates |
| 15 | Decisions (below) | you |
| 16 | Tunnel watchdog window (v1.1) | you start it; it reports only unless given the key and `-RestartStuck` |
| 17 | Stop the laptop sleeping on AC power (v1.1): all three stalls of 24 Nov were standby | three `powercfg` lines |
| 18 | The A100's real numbers on the status page (v1.1) | the QA server on the VM (item 6) and one more forwarded port |
| 19 | Two or three dense recordings of about 10 minutes, your own content, for the Live replay (v1.1 WS1) | the files in `data-v1\eval\dense\`; hosted speech-to-text for the minutes replayed |
| 20 | Which English voice (`V1_EN_VOICE`), and whether the session should move to the copy by itself when the stock voice fails (v1.1 WS2) | your ears and a decision |
| 21 | The session start measured with a recorded voice (Streamer Mode), a male speaker, and the English voices on a night the hosted voice is healthy (v1.1 WS2) | a voice recorded in v1 with consent; hosted calls for about 20 short sessions |
| 22 | A second heard-back judge for Tamil, Bengali and the other languages (v1.1 WS3): the QA server's Whisper | item 6 |
| 23 | Labels on `/studio/calibrate` (v1.1 WS3) | thirty per language from a speaker of it |
| 24 | Five comparison backends left running on 8111-8115 (v1.1 WS3) | three PowerShell lines; they could not be stopped from inside this work |
| 25 | A pitch video of a real stream, and how long recordings are kept (v1.1 WS4) | the speaker's agreement, the flag on 8110, a decision on deletion |
| 26 | Listeners for the blind listening test (v1.1 WS4) | WS5's pairs; people who speak the language |
| 28 | Get written confirmation of commercial use from AI4Bharat / legal review (v1.2 Part 1; `NEEDS_APPROVAL.md` item 28) | a written answer from AI4Bharat, or a lawyer's read of IndicF5's lineage |

## 4. Decisions needed

1. **Licences.** Indic Transcribe: hosting it as a service others call needs its authors' written sign-off; fine
   for samples. The speaker-similarity model behind earlier numbers (ECAPA2) is non-commercial; the QA server
   uses an Apache-2.0 one, whose scale has to be measured before a threshold is set. pyannote needs its terms
   accepted and attribution. Maya 2 (Apache-2.0), Gemma 4 (Apache-2.0), Whisper (MIT) are clear. **IndicF5 is not
   clear (26 Nov 2026): legal confirmation needed.** Its card says MIT, but a model fine-tuned from it says the
   lineage is non-commercial (`MODELS.md`, "Checked on 26 Nov 2026"; `NEEDS_APPROVAL.md` item 28).
2. **Maya 2: keep or drop.** Not loaded, so not heard. It has no speed control and needs the sample's exact
   words, like IndicF5; it adds English. Decide after an HQ window with it.
3. **Quantised big model or the hosted one for Studio's review.** Not measured: the big model is not loaded. The
   routing file reviews with the hosted model until then. Sizes on offer: 12B (10.3 GB) or 31B (23.3 GB).
4. **Which Live flags to switch on** (section 2: two are "your call").
5. **Where v1 runs.** On the VM (items 2-4) before any number here is quoted as the product's.
6. **Studio HQ's transcript steps (v1.1 WS3).** With the new flags off, HQ's "merge the hearings" and "clean"
   steps damaged the transcript of two of three test videos on both days they ran (every line holding the line
   before it; a transcript in Latin letters with first words lost). `V1_HQ_REVIEW` puts such lines back. Decide
   whether HQ may be offered at all without it, and whether the second hearing by our Whisper is worth keeping:
   it is the source of the Latin lines, and the hosted hearing measured better on the same audio (section 3
   of `EVAL_REPORT.md`).
7. **What "96% heard back" should mean (v1.1 WS3).** The judge counts a spelling it writes differently as a
   word not heard, and counts a dub of the wrong sentence as heard. Until someone has labelled lines on
   `/studio/calibrate`, neither the 96% target nor the flag line of 90% is tied to what a listener hears.

## 5. Start v1 and run the demo check

On the laptop, as it was run here (PowerShell, from the v1 checkout):

```powershell
powershell -File scripts\v1\run-local.ps1          # backend 8110 in its own window, website 3100 in this one
```

then, in Git Bash:

```bash
scripts/v1/demo-check.sh      # READY / NOT READY
scripts/v1/warmup.sh          # one small request through every service
scripts/v1/v0-check.sh        # v0 still answers
```

On the VM (after items 1-3):

```bash
cd /srv/bharatdb-v1/app && scripts/v1/run-local.sh && scripts/v1/demo-check.sh && scripts/v1/warmup.sh
```

Open `http://localhost:3100/health`, `/metrics-ui`, `/studio` (the HQ choice shows when `V1_STUDIO_HQ=true`).
Flags are in `backend/.env` of the v1 checkout; restart the backend after a change. Roll back: switch the flag
off, or stop v1; v0 on 3000 and 8010 is as it was.

## 6. v1.1 WS5: GPU upgrades are ready for you to deploy (25 Nov 2026)

Nothing was run on the GPU machine. What exists now:

- **`NEEDS_APPROVAL.md` is one checklist of 24 items, top to bottom**, renumbered (the numbers in sections 3 and 4
  above are the old ones; the table at its end translates). Item 2, the backend on the machine, is first.
- **A deploy kit** (`gpu_engine_v1/deploy/`): each new model server is copy, `start.sh <server>`,
  `smoke.sh <server>`. It reads `nvidia-smi` and refuses unless 4 GB stays free, never touches CUDA MPS or v0's
  servers, and stops only what it started. No Docker, no sudo.
- **The QA server runs on CPU** with a speaker model whose licence allows commercial use (Apache-2.0, checked);
  a comparison of two 7 s clips took 765 ms on the laptop's CPU (one run, 20 comparisons, range 727-797 ms).
- **Two A/B kits**, both waiting for the machine: Maya 2 against IndicF5 on 20 lines with 6 English ones (for the
  blind listening page), and the 12B translation model against the small one on 120 lines with a rule for "wins"
  that is written down before any result.
- **Two things to know before the big model:** by the estimates 31B does not fit on this card beside the voice
  engines; and the 12B checkpoint's own page reports start failures on vLLM with no version named as working, so
  its first start is a test in itself.
