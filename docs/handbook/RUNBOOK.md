# Runbook

Operations summary, dated 2026-11-25. This page points to the detailed sources and does not repeat them:

- [`../v1/RUNBOOK.md`](../v1/RUNBOOK.md): start, stop, check, auto mode and its overrides, the flags of manual mode, routing, GPU modes, rollback, backup, deploy kit.
- [`../v1/NEEDS_APPROVAL.md`](../v1/NEEDS_APPROVAL.md): the 26-item checklist with exact commands. **It holds the
  GPU VM's address and the SSH command lines. Never copy them into another file, a log, a chat or a commit.**
- v0's GPU engine notes (read-only reference): `gpu_engine/README.md` in the v0 folder.

Hard rules while operating: v0 (3000, 8010, 9001-9040) is never stopped, restarted or reconfigured from v1 work;
CUDA MPS on the VM is never touched; one GPU through one tunnel is one stream (SPEC section 21).

## Run v0

v0 is the product people use. Folder `Desktop\BharatDUB`, branch `main`, tag `v0-baseline` (`80c36d8`).

| What | Command (PowerShell, in the v0 folder) | Port |
|---|---|---|
| Backend + website, real providers | `.\dev.ps1` (needs `backend\.env` with keys) | 8010 (backend), 3000 (web) on the dev laptop |
| Same, mock providers, no keys | `.\dev.ps1 -Mock` (data in `backend\data-mock`) | same |
| Tunnels to the GPU VM | `.\gpu_engine\tunnel.ps1 -Key <key file> -Target <user@vm>` (values: NEEDS_APPROVAL) | forwards 9001-9003, 9010, 9020, 9030, 9040 |

`PUBLIC_API_BASE` must match the backend port (8010 on the dev laptop), or the Studio A/B player has no video
(SPEC section 16). Restarting the dev servers on Windows: kill the leftover child process by its PID; a rebuild of
the website needs `NEXT_PUBLIC_*` set.

VM engines after a VM restart (v0's scripts, in its engine folder on the VM): `start_live.sh` (voice + MPS),
`start_sep.sh`, `start_stt.sh`, `start_llm.sh` (about 2 minutes). See v0's `gpu_engine/README.md`. They do not
start by themselves.

## Run v1

Folder `Desktop\BharatDUB-v1`, branch `v1`. Data in `data-v1\` (git-ignored). Own `backend\.env`.

```powershell
powershell -File scripts\v1\run-local.ps1          # backend 8110 (own window), website 3100; refuses 3000/8010
```

Then in Git Bash, from the v1 folder:

```bash
scripts/v1/demo-check.sh      # READY / NOT READY: backend, website, model servers, hosted services, GPU, the mode and what is in force, nobody else live
scripts/v1/warmup.sh          # one small request through each service; prints each time
scripts/v1/v0-check.sh        # v0 still answers (read-only)
scripts/v1/gpu-mode.sh status # which model servers answer, free GPU memory, who is live (read-only)
```

Pages: `http://localhost:3100/health`, `/metrics-ui`. Stop: `scripts/v1/stop-local.sh` (or close the windows).
Details: `../v1/RUNBOOK.md` sections 1-2.

## Mode, overrides, flags

**v1 runs in auto mode (v1.2, [ADR-0036](adr/0036-auto-mode.md)): nobody manages switches.** `V1_MODE=auto` is the
default; `backend/app/v1/mode.py` is the one place that says what is in force; the per-feature `V1_*` lines in
`backend/.env` are not read. Details, thresholds and where to look: `../v1/RUNBOOK.md` section 3.

| In auto mode | What |
|---|---|
| Always on | trace, router, API log, breakers and ladder, stock voices for a `/live` session without a streamer profile, Studio HQ with its review, 1.15x fit limit, adaptive takes, normaliser, a job's glossary, the HQ judge |
| Auto budget | the Live duration budget applies to a language only while its dub is behind or speech is dense; else the full translation. A sample of lines is judged for lost meaning; a language over 25% gets a looser budget |
| English | one voice per session, chosen once at the start from a timed probe of the copied voice |
| A refused line | asked again, then spoken by another voice; only when every voice fails is it marked `unspoken`, and logged |
| Guards | script guard on every translated line; content shift on every Studio line and on a sample of Live lines |

**Measured on 26 Nov 2026** ([EXP-031](experiments/EXP-031-auto-mode-dense-reel.md),
[EXP-032](experiments/EXP-032-auto-mode-studio.md)): on dense Live speech auto mode as shipped is worse than manual
mode with `V1_LIVE_BUDGET=true` (66.3% against 79.1% within 0.25 s, 82.4% against 90.0% within 1 s; 5 runs each).
Largest cause: stock voices on `/live`; then the breakers on a link that hiccups; then the meaning check loosening
nearly every session. With `live_stock_default: off`, `breaker: off` and `live_degrade: off` it measured 74.2% and
88.5%, without protection in a real stall. The founder's choices: `../v1/NEEDS_APPROVAL.md` item 29. No threshold
was changed. Studio HQ in auto mode: 95.6% of words heard back, 152 s a video.

**To switch ONE behaviour off:** `backend/config/overrides.yaml` (every entry is commented out as shipped; read
once at start; a bad file is logged and ignored). Remove the `# ` in front of the line, restart the backend.

| Entry | Effect |
|---|---|
| `trace`, `router`, `api_log`, `breaker`, `live_degrade`, `fit_115`, `hq_adaptive`, `hq_normalise`, `hq_auto_glossary`, `hq_judge`: `off` | that behaviour as before it existed |
| `live_stock_default: off` | `/live` may copy the voice on the stream again (consent tick) |
| `studio_hq: off` | HQ is not offered (`hq_review: off` has no effect while HQ is on) |
| `live_budget: off` / `auto_budget: off` / `meaning_check: off` | no budget at all / the budget on every phrase as in v1.1 / no budget is loosened |
| `en_single_voice: off` / `en_auto: off` / `en_voice: stock` or `copy` | English line by line again / no probe / the voice pinned |
| `voice_fallback: off`, `script_guard: off`, `shift_check: off` | that part of v1.2 off |
| `live_record: off`, `hq_calibrate: off`, `listen_test: off` | no recordings / that page answers 404 |
| `tts_server`, `tts_maya`, `live_late_shorten`, `live_backcheck`: `on` | not part of auto mode; for a trial only |

**Manual mode** (`V1_MODE=manual`, restart): every feature follows its own `V1_*` flag as before v1.2, all off by
default except `V1_HQ_ADAPTIVE`; with everything off v1 behaves as v0; what v1.2 added is off; the overrides file is
not read. It is the mode of comparison backends, baselines and the tests. The measured reason behind each flag:
`../v1/RUNBOOK.md` section 3.4. Removed in v1.2 ([ADR-0037](adr/0037-removed-dead-features.md)): the dynamic first
phrase, the engine-speed flag, the session warm start and the controller's own switch; an env line that still sets
one is ignored.

| Set | Value | Reason |
|---|---|---|
| Store | `V1_STORE=json` | Postgres never run |

Watch out: in auto mode stock voices are always on for a `/live` session without a streamer profile, so it never
learns a voice and its consent tick has no effect; every v1.1 Live number was measured with a learned voice. The only v1 stock-voice runs: first audio p50 5.1 s and
58.3% within 1 s, against 2.34 s and 83.3% with the learned voice (V1_1_SUMMARY section 3, **measured**, 3 runs).
`V1_HQ_ADAPTIVE` was the one flag the sources disagreed on (on in one, off in three). The founder decided on
26 Nov 2026: **on**. [V1_1_SUMMARY](../v1/V1_1_SUMMARY.md) section 3, [the v1 runbook](../v1/RUNBOOK.md) section 3,
[the v1 summary](../v1/SUMMARY.md) and `backend/.env.example` now say the same, with the same measured reason, and
the code's default is on ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) question 20, closed).

Kept Live recordings (`V1_LIVE_RECORD`): deleted by themselves after `V1_RECORD_KEEP_DAYS` (30) days; list and
delete on `/live` or `GET` / `DELETE /api/v1/recordings` ([ADR-0034](adr/0034-recording-retention.md)).

## Deploy a new model server on the GPU VM

Kit: `gpu_engine_v1/deploy/` (`start.sh`, `smoke.sh`, `stop.sh`, `status.sh`; `kit.py`). Full steps:
`../v1/RUNBOOK.md` section 8 and NEEDS_APPROVAL items 4, 8-11. Never run yet with a real model, never on Linux.

1. Card first: read `nvidia-smi`. **4 GB rule:** a server may start only when free memory minus its need is at
   least 4 GB. The kit checks this itself and refuses otherwise.
2. Copy `gpu_engine_v1` to the VM; `bash ~/gpu_engine_v1/deploy/start.sh <qa|tts|maya|transcribe|big-llm>`
   (`--dry-run` first prints every command).
3. `bash ~/gpu_engine_v1/deploy/smoke.sh <server>`: PASS/FAIL per check and the memory held. Note the memory and
   use `--need-gb <measured>` from then on.
4. Set the server's URL in v1's `backend/.env` (`V1_QA_URL`, `V1_TTS_SERVER_URL`, `V1_MAYA_URL`,
   `V1_TRANSCRIBE_URL`, `V1_BIG_LLM_URL`) and restart the v1 backend. A tunnel for 9041-9045 is needed while the
   backend is on the laptop.
5. Undo: `bash ~/gpu_engine_v1/deploy/stop.sh <server>` (stops only its own pid) and empty the URL.

Servers that need more than about 6 GB (Maya 2, Indic Transcribe, big model) run only inside an **HQ window**,
which stops v0's Gemma on 9020: founder's command, nobody live, closed by v0's `start_llm.sh`.

## Roll back

v0 was never changed, so rollback is using v0's ports again.

| Problem | Action |
|---|---|
| One v1 behaviour misbehaves | its line in `backend/config/overrides.yaml` (manual mode: its flag), restart the v1 backend |
| v1 as a whole | `scripts/v1/stop-local.sh`; use 3000/8010 |
| Code | tag `v0-baseline` = `80c36d8` |
| Card stuck in an HQ window | `scripts/v1/gpu-mode.sh normal --run`, else v0's `start_llm.sh`; meanwhile translation goes to Gemini |
| A deployed v1 model server | `deploy/stop.sh <server>`, empty its URL |

## Backup

- `scripts/v1/backup.sh` (`V1_BACKUP_BUCKET=gs://...`, `--dry` first) copies the store, voice samples, trace,
  routing and compose files and the names of settings, never keys, cache, uploads or renders. Needs a bucket and a
  signed-in `gcloud`: **not done** (NEEDS_APPROVAL item 15). The restore in `../v1/RUNBOOK.md` section 7 has never
  been rehearsed; a VM disk snapshot is the founder's to take.
- Until then the only copies of `data-v1\` and v0's `backend\data` are on the laptop.
- Never write the local store from a script while its backend runs: the backend writes its own copy back
  ([INC-03](INCIDENTS.md#inc-03-stale-voice-profile-text-written-back-by-server)).

## Demo-day checklist

| # | Check | Why / source |
|---|---|---|
| 1 | Laptop on the charger, sleep on AC off, lid action "do nothing" | all three stalls of 24 Nov were standby ([INC-05](INCIDENTS.md#inc-05-link-stalls-of-24-nov)); NEEDS_APPROVAL item 16 |
| 2 | PC clock correct: compare `date` with a server's `Date` header | a wrong clock broke every hosted call ([INC-01](INCIDENTS.md#inc-01-wrong-pc-clock)) |
| 3 | Tunnels up, one per kind of traffic (v0 `tunnel.ps1` window open) | [INC-04](INCIDENTS.md#inc-04-tunnel-stalls-on-the-67-min-stream) |
| 4 | VM engines answer (`gpu-mode.sh status`); card in normal mode, not an HQ window | `../v1/RUNBOOK.md` section 2 |
| 5 | `scripts/v1/demo-check.sh` says READY, 15 minutes ahead | same |
| 6 | `scripts/v1/warmup.sh` run | same |
| 7 | Stream watcher open: `powershell -File scripts\v1\stream-watch.ps1 -Window` (restart it after an update) | shows ENGINE/LINK/CIRCUIT/RUNG lines |
| 8 | `GET /api/v1/flags` says `V1_MODE: auto` and shows no override you did not mean; backend restarted after the last change | section above |
| 9 | No comparison backends left on 8111-8115 (`Get-NetTCPConnection -LocalPort 8111,8112,8113,8114,8115 -State Listen`) | NEEDS_APPROVAL item 18 |
| 10 | Nobody else live on v0 or v1; no replay or A/B run in progress | one GPU through one tunnel is one stream; the hosted account takes one request at a time |
| 11 | Hosted services healthy (the health panel shows "key set", not whether the service answers: try one line) | [INC-02](INCIDENTS.md#inc-02-hosted-stt-outage), [INC-06](INCIDENTS.md#inc-06-hosted-stock-voice-refusing-lines-http-502) |
| 12 | Streamer wears headphones; tab-only capture (window/screen share loops the dub back) | SPEC sections 9 and 16 |

## If the VM's address changes

The address is never written in code or env files on the laptop. Where it is used:

| Place | What to change |
|---|---|
| v0 `gpu_engine\tunnel.ps1` | nothing in the file: the address is its `-Target user@host` argument at start |
| `scripts\v1\tunnel-watchdog.ps1` | its `-Target` argument (only when it is asked to dial) |
| `docs/v1/NEEDS_APPROVAL.md` | the SSH lines in it (the one file that holds the address) |
| `backend/.env` (v0 and v1): `GPU_VOICE_URL`, `GPU_SEPARATE_URL`, `GPU_STT_URL`, `GPU_LLM_URL`, and v1's `V1_*_URL` | these point at the local ends of the tunnels, so they should not change (verify the values; never print them) |

The tunnel uses `BatchMode=yes`, so ssh cannot ask to accept a new host key: connect once by hand first
(inferred from `tunnel.ps1`'s options; unconfirmed). A new machine also needs the engines rebuilt
(v0's `setup_machine.sh`, `setup_gpu_mode.sh`; IndicF5 is gated, sign in first), as on 20 Nov 2026 (SPEC section 17).

## Stream watcher

`scripts/v1/stream-watch.ps1` (`-Window` for its own window) watches every live session on v0 (8010) and v1 (8110),
read-only. Output in `data-v1\streamwatch\`: `events.log`, a CSV row every 20 s per stream, a summary per language
when a stream ends; `scripts/v1/collect-logs.py` copies them into `logs/streams/`.

Reading `events.log`: `LINK STALL` with the **hosted** services in the list means this PC was away (asleep), not the
tunnel. `ENGINE DOWN` for only the GPU services means the tunnel or a VM server. With `V1_BREAKER` and
`V1_LIVE_DEGRADE`: `CIRCUIT OPEN/CLOSED`, `CIRCUIT LINK STALL/BACK`, `RUNG [backend session] a -> b (why)`.
`scripts\v1\tunnel-watchdog.ps1` (NEEDS_APPROVAL item 17, not run yet) tells a sleeping PC, a dead tunnel, a stuck
ssh and a dead VM server apart.
