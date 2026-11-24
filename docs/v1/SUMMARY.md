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
| New model servers | batching voice server, Maya 2, Indic Transcribe, QA, big translation model: code, containers, stub mode | stubs tested; **no real model loaded** (GPU memory, licences) |
| Eval | Live comparison across backends, Studio standard against HQ, key words on the hard set, one script for all | works; `EVAL_REPORT.md` |
| Operations | demo check, warm-up, backup, GPU mode switch, runbook | demo check and warm-up ran; backup and mode switch not run |
| Tests | 61 new tests; 159 pass in all, 1 skipped (Postgres store: no database here) | |

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
  `V1_LLM_PREFIX_CACHE`.

## 2. Flags: what the measurements say

Numbers are from `EVAL_REPORT.md` (three runs per Live setup, one run per Studio video on three videos).

| Flag | Measured | Recommendation |
|---|---|---|
| `V1_TRACE` | on in every run; no error from it | **on** |
| `V1_ROUTER` | same providers as with it off; first audio 2.4 s against 2.3-2.7 s | **on** (needed for the HQ path's provider lists to be changed in one file) |
| `V1_STUDIO_HQ` | words heard back 92.5% (91.1-93.5) against 89.2% (84.9-93.4) for standard; about 3 times the time (255 s against 82 s for a 50 s video); a third of the lines flagged | **on** as a choice per job; use it for samples. It is under the 96% target |
| `V1_FIT_115` | on in the HQ runs: largest speed-up 1.15x; the test videos hardly needed speeding up | on with HQ; its effect on videos that need more speed-up is covered by tests only |
| `V1_PHRASE_DYNAMIC` | session's first audio 1.7 s earlier when a voice is ready at the start (5.9 -> 4.1 s, stock voices); no gain with a voice learned from the stream; 5 points fewer phrases on time on dense speech (69.6% -> 64.5%) | **your call**: worth it for a streamer's opening line, costs timing afterwards |
| `V1_LIVE_LATE_SHORTEN` | 1-3 lines a run said shorter, skips 4.7 -> 1.7 a run | **your call**: fewer lost lines; measured only inside a bundle whose timing was worse |
| `LIVE_FIT_MAX_TEMPO=1.2` | phrases at the limit 20 -> 25 | off until someone hears 1.2x against 1.3x |
| `V1_SPEC_TRANSLATE` | 0 early translations used in 5 runs | **off** |
| `V1_LLM_PREFIX_CACHE` | cache share 61.4% both ways; no faster | **off** (the server's cache was already on) |
| `V1_LIVE_BACKCHECK` | not measurable without the QA server | off until the QA server runs |
| `V1_LIVE_STOCK_DEFAULT` | a product rule, not a speed change | **your call** |
| `V1_TTS_SERVER`, `V1_TTS_MAYA` | servers not loaded | off |
| `V1_STORE=postgres` | never run against a database | `json` |

Against the targets: Studio words heard back 92.5% (target 96%): not reached. Live first audio 2.3-2.5 s through
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

## 4. Decisions needed

1. **Licences.** Indic Transcribe: hosting it as a service others call needs its authors' written sign-off; fine
   for samples. The speaker-similarity model behind earlier numbers (ECAPA2) is non-commercial; the QA server
   uses an Apache-2.0 one, whose scale has to be measured before a threshold is set. pyannote needs its terms
   accepted and attribution. IndicF5 (MIT), Maya 2 (Apache-2.0), Gemma 4 (Apache-2.0), Whisper (MIT) are clear.
2. **Maya 2: keep or drop.** Not loaded, so not heard. It has no speed control and needs the sample's exact
   words, like IndicF5; it adds English. Decide after an HQ window with it.
3. **Quantised big model or the hosted one for Studio's review.** Not measured: the big model is not loaded. The
   routing file reviews with the hosted model until then. Sizes on offer: 12B (10.3 GB) or 31B (23.3 GB).
4. **Which Live flags to switch on** (section 2: two are "your call").
5. **Where v1 runs.** On the VM (items 2-4) before any number here is quoted as the product's.

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
