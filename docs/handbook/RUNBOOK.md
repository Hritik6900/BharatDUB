# Runbook

Operations summary, dated 2026-11-25. This page points to the detailed sources and does not repeat them:

- [`../v1/RUNBOOK.md`](../v1/RUNBOOK.md): start, stop, check, flags, routing, GPU modes, rollback, backup, deploy kit.
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
scripts/v1/demo-check.sh      # READY / NOT READY: backend, website, model servers, hosted services, GPU, flags, nobody else live
scripts/v1/warmup.sh          # one small request through each service; prints each time
scripts/v1/v0-check.sh        # v0 still answers (read-only)
scripts/v1/gpu-mode.sh status # which model servers answer, free GPU memory, who is live (read-only)
```

Pages: `http://localhost:3100/health`, `/metrics-ui`. Stop: `scripts/v1/stop-local.sh` (or close the windows).
Details: `../v1/RUNBOOK.md` sections 1-2.

## Flags and the recommended v1 env

All flags default off; with all off v1 behaves as v0. Restart the backend after a change. Every flag with its
effect and measured reason: `../v1/RUNBOOK.md` section 3; a ready block is at the end of `backend/.env.example`.
Summary from `docs/v1/V1_1_SUMMARY.md` section 3 (nothing new measured for this list):

| Set | Flags | Reason (source) |
|---|---|---|
| **On** | `V1_TRACE`, `V1_ROUTER`, `V1_API_LOG`, `V1_STUDIO_HQ`, `V1_FIT_115`, `V1_LIVE_STOCK_DEFAULT` | the list that was asked for |
| **On with HQ** | `V1_HQ_REVIEW`, `V1_HQ_JUDGE` | HQ without the review dubbed 2 of 3 test videos from a damaged transcript (25 of 38 lines vs 0), [INC-07](INCIDENTS.md#inc-07-hq-transcript-damage-found) |
| **Founder's call, recommended on** | `V1_BREAKER` + `V1_LIVE_DEGRADE` (together) | 50 s stall: 4 of 22 phrases dubbed with them off (1 run), all with them on (3 runs) (**measured**, relay, 24 Nov) |
| **Founder's call** | `V1_LIVE_BUDGET` (one switch for all languages) | within 1 s 86.5% -> 92.3% (dense reel, 5 runs); Tamil lost meaning in 7 of 20 lines read |
| **On once a voice is chosen** | `V1_EN_SINGLE_VOICE` with `V1_EN_VOICE` | NEEDS_APPROVAL item 22 |
| **On when used** | `V1_HQ_CALIBRATE`, `V1_LISTEN_TEST` | pages only; no labels, no pairs yet |
| **Off** | `V1_LIVE_RATECTRL`, `V1_LIVE_NATIVE_SPEED`, `V1_LIVE_WARMSTART`, `V1_PHRASE_DYNAMIC`, `V1_LIVE_LATE_SHORTEN`, `V1_LIVE_BACKCHECK`, `V1_TTS_SERVER`, `V1_TTS_MAYA`, `V1_HQ_ADAPTIVE`, `V1_HQ_NORMALISE`, `V1_HQ_AUTO_GLOSSARY`, `V1_LIVE_RECORD` | no proven gain, not measurable yet, or server not loaded |
| Store | `V1_STORE=json` | Postgres never run |

Watch out: with `V1_LIVE_STOCK_DEFAULT` on, a `/live` session without a streamer profile never learns a voice;
every v1.1 Live number was measured with a learned voice. The only v1 stock-voice runs: first audio p50 5.1 s and
58.3% within 1 s, against 2.34 s and 83.3% with the learned voice (V1_1_SUMMARY section 3, **measured**, 3 runs).
Note: the sources disagree on `V1_HQ_ADAPTIVE`. [V1_1_SUMMARY](../v1/V1_1_SUMMARY.md) section 3 says "on"
(61% less voice time against five fixed takes); [the v1 runbook](../v1/RUNBOOK.md) section 3, [the v1 summary](../v1/SUMMARY.md)
and `backend/.env.example` say "off" (against v1's own rule it makes the same 143 takes). This handbook keeps
"off" until the founder decides ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md), [NEEDS_APPROVAL item 27](../v1/NEEDS_APPROVAL.md)).

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
| One v1 behaviour misbehaves | switch its flag off, restart the v1 backend |
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
| 8 | Flags as recommended above; backend restarted after the last change | section above |
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
