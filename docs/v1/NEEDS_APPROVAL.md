# v1: needs approval

Work that was deferred because it needs the GPU VM, a forbidden command, or a decision. Each entry: what, why, exact commands, expected GPU memory, rollback.

## 1. Find v0's processes and paths on the VM, and measure GPU memory per process

- **What:** list the processes behind ports 9001-9003, 9010, 9020, 9030 (9040 is off), their code folders, and the
  GPU memory each one holds.
- **Why deferred:** this build ran on the laptop; no shell on the VM was used (the tunnel and SSH were not to be
  touched).
- **Commands (read-only, on the VM):**
  ```bash
  ss -ltnp | grep -E ':(900[1-3]|9010|9020|9021|9030|9040)\b'
  ps -eo pid,etimes,cmd | grep -E 'voice_engine|sep_engine|stt_engine|vllm|mio_engine' | grep -v grep
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
  nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv
  ```
- **Expected GPU memory:** none (read-only).
- **Then:** put the paths into the local rules file as read-only, and replace the table in `DISCOVERY.md` section 6.
  Known so far: the engines were installed under `~/voice_engine` for user `ocr`.
- **Rollback:** nothing to roll back.

## 2. Docker on the VM

- **What:** `docker-compose.v1.yml` (project `bharatdb-v1`) needs Docker Engine with the compose plugin and, for
  GPU containers, the NVIDIA container toolkit.
- **Why deferred:** installing them needs `sudo` and system packages (forbidden), and it is not known whether they
  are already there. The laptop has no Docker, so the compose file was written but never run.
- **Commands (check first):**
  ```bash
  docker --version && docker compose version
  docker info | grep -i -E 'runtimes|nvidia'
  ```
  If missing (the user runs these): Docker's own install guide for the VM's distribution, then
  `sudo usermod -aG docker ocr`, then the NVIDIA container toolkit guide.
- **Meanwhile:** `scripts/v1/run-local.sh` starts the v1 backend and website without containers.
- **Expected GPU memory:** none. **Rollback:** `docker compose -p bharatdb-v1 -f docker-compose.v1.yml down`.

## 3. Put v1 on the VM

- **What:** v1 was built and run on the laptop (backend 8110, website 3100, engines through the SSH forwards).
  The design has it on the VM, next to the engines.
- **Why deferred:** needs a shell on the VM, and `/srv/bharatdb-v1` needs `sudo` once.
- **Commands (the user runs the first two lines):**
  ```bash
  sudo mkdir -p /srv/bharatdb-v1/data && sudo chown -R $USER /srv/bharatdb-v1
  cd /srv/bharatdb-v1 && git clone <repo url> app && cd app && git checkout v1
  cp backend/.env.example backend/.env      # fill in the keys; DATA_DIR=/srv/bharatdb-v1/data
  scripts/v1/run-local.sh                    # without containers
  # or, with Docker (item 2): cp .env.v1.example .env.v1 && docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 up -d --build
  scripts/v1/demo-check.sh
  ```
- **Expected GPU memory:** none (the backend's Demucs and VAD fallbacks run on CPU).
- **Rollback:** `scripts/v1/stop-local.sh` or `docker compose -p bharatdb-v1 -f docker-compose.v1.yml down`. v0 is
  not involved.

## 4. Domain, HTTPS and the demo password

- **What:** the `https` profile of the compose file (Caddy) needs a domain whose DNS points at the VM, ports 80
  and 443 open in the VM's firewall, and a password hash.
- **Why deferred:** DNS, firewall and cloud console changes are forbidden here.
- **Commands:**
  ```bash
  docker run --rm caddy:2.8-alpine caddy hash-password --plaintext '<the demo password>'
  # in .env.v1: V1_DOMAIN=<domain>  V1_DEMO_PASSWORD_HASH='<hash>'
  #             V1_PUBLIC_ORIGIN=https://<domain>  V1_PUBLIC_WS_ORIGIN=wss://<domain>
  docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 --profile https up -d --build
  ```
- **Note:** a browser gives the microphone only to an HTTPS page or to `localhost`. Until there is a domain, the
  site works through an SSH forward of 3100 and 8110 to the laptop's `localhost`.
- **Rollback:** `docker compose ... --profile https down`.

## 5. Postgres store (`V1_STORE=postgres`)

- **What:** `backend/app/v1/store_pg.py` keeps the store's rows in Postgres.
- **Why deferred:** there was no database to run it against, so it has never been executed. Treat it as untested.
- **Commands:**
  ```bash
  docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 --profile postgres up -d postgres
  # backend/.env: V1_STORE=postgres  POSTGRES_DSN=postgresql://bharatdb:<password>@127.0.0.1:5440/bharatdb
  cd backend && TEST_POSTGRES_DSN=postgresql://bharatdb:<password>@127.0.0.1:5440/bharatdb python -m pytest tests/test_v1_store.py -q
  ```
- **Rollback:** `V1_STORE=json` (the default). The JSON file is not migrated or deleted by switching.

## 6. QA server on the VM's CPU (:9045): back-check and speaker similarity

- **What:** start `gpu_engine_v1/qa_server.py` with its real models (Whisper large-v3-turbo through
  faster-whisper, SpeechBrain ECAPA) on CPU. It makes Studio HQ's speaker-similarity score possible, gives a
  back-check that does not use the hosted one-request account, and is the scorer of the live back-check.
- **Why deferred:** needs a shell on the VM (and Docker, item 2, or a Python environment there). About 2 GB of
  model downloads. No licence question: MIT and Apache-2.0.
- **Commands:**
  ```bash
  docker compose -p bharatdb-v1-models -f gpu_engine_v1/docker-compose.models.yml --profile qa up -d --build
  curl -s http://127.0.0.1:9045/health
  # v1 backend/.env:  V1_QA_URL=http://127.0.0.1:9045
  ```
- **Expected GPU memory:** 0 (CPU). With `QA_DEVICE=cuda` about 2-5 GB (not measured): do not use while the card
  has under 9 GB free.
- **Decision inside:** speaker similarity used ECAPA2 in earlier measurements; that model is non-commercial
  (CC-BY-NC-4.0). The server uses SpeechBrain ECAPA instead; measure the real-person baseline again before any
  threshold is set (`V1_HQ_SIMILARITY_MIN`).
- **Rollback:** `docker compose ... --profile qa stop qa`; empty `V1_QA_URL`. Scoring falls back to the hosted
  speech-to-text (words only).

## 7. Voice server with batching (:9041), `V1_TTS_SERVER`

- **What:** one IndicF5 process that batches lines, to replace v0's three processes (about 12 GB) for v1.
- **Why deferred:** GPU memory. About 6 GB is free and the model's process is expected to need about 4 GB, which
  leaves under the 4 GB of headroom the rule asks for. Also: the batched path has never run (written from the
  library's interface) and must be compared with v0's audio first.
- **Commands (when the card has at least 8 GB free, for example with Indic-Mio and one of nothing else loaded):**
  ```bash
  nvidia-smi --query-gpu=memory.free --format=csv
  docker compose -p bharatdb-v1-models -f gpu_engine_v1/docker-compose.models.yml --profile tts up -d --build
  curl -s http://127.0.0.1:9041/health          # batching, batch_errors
  # compare: same sample and line through 9001 and 9041, listen, and check `largest_batch` >= 2 under load
  # v1 backend/.env:  V1_TTS_SERVER_URL=http://127.0.0.1:9041   V1_TTS_SERVER=true
  ```
- **Expected GPU memory:** about 4 GB (v0's engines report 1.43 GB of tensors each; process totals not measured).
- **Rollback:** `V1_TTS_SERVER=false` (v1 goes back to 9001-9003 at once), then stop the container.

## 8. Indic Transcribe (:9043)

- **What:** second speech-to-text for Studio HQ (two hearings, merged by the translation model).
- **Why deferred:** (a) GPU memory: 9.2 GiB by its card, so only inside an HQ window; (b) licence: hosting it as
  a service others call needs the authors' written sign-off (`MODELS.md`); (c) the model is gated: its terms must
  be accepted on Hugging Face by the account whose token is used.
- **Commands (inside an HQ window, after the licence decision):**
  ```bash
  export HF_TOKEN=...   # an account that accepted the model's terms; never commit it
  docker compose -p bharatdb-v1-models -f gpu_engine_v1/docker-compose.models.yml --profile transcribe up -d --build
  # v1 backend/.env:  V1_TRANSCRIBE_URL=http://127.0.0.1:9043
  ```
- **Expected GPU memory:** about 9 GB. **Rollback:** stop the container, empty `V1_TRANSCRIBE_URL`; HQ then hears
  with the hosted speech-to-text only.

## 9. Big translation model (:9044) and the HQ window

- **What:** `scripts/v1/gpu-mode.sh hq --run` stops the small translation model (:9020) and starts a larger
  Gemma 4 (4-bit QAT) on :9044; `normal --run` reverses it. During the window v0 and v1 Live translate through the
  hosted model by themselves.
- **Why deferred:** stopping a v0 server is forbidden here, and the script itself is on the list of commands not
  to be run, so not even its dry run was executed: it was checked with `bash -n` and its read-only `status`
  ran. Also open: which size (12B, 10.3 GB on disk; or 31B, 23.3 GB), and the vLLM image tag (`VLLM_TAG`): the
  vLLM recipe for Gemma 4 names no minimum release.
- **Commands (when nobody is live):**
  ```bash
  scripts/v1/gpu-mode.sh status
  scripts/v1/gpu-mode.sh hq             # prints what it would do
  VLLM_TAG=<release> scripts/v1/gpu-mode.sh hq --run
  # v1 backend/.env:  V1_BIG_LLM_URL=http://127.0.0.1:9044/v1
  scripts/v1/gpu-mode.sh normal --run   # afterwards
  ```
- **Expected GPU memory:** the window frees about 18 GB; 12B needs about 11-14 GB, 31B about 20-23 GB plus its
  cache (estimates from the weights; measure with `nvidia-smi` on the first run).
- **Rollback:** `scripts/v1/gpu-mode.sh normal --run`. If :9020 does not come back, v0 keeps translating through
  the hosted model; start it with v0's own `start_llm.sh`.
- **Before trusting it:** translate the eval lines with it and with the hosted model and compare; nobody has
  published how the 4-bit models do on Hinglish into Indian languages.

## 10. Maya 2 (:9042), `V1_TTS_MAYA`

- **What:** a second candidate voice for Studio HQ's N-best.
- **Why deferred:** GPU memory (7.7 GB steady, 9.2 GB while loading, by its card): only inside an HQ window and
  not together with the 31B model. Never run here; its server was written from the model card's example.
- **Commands:** `docker compose ... --profile maya up -d --build`, then `V1_MAYA_URL=http://127.0.0.1:9042` and
  `V1_TTS_MAYA=true`. **Rollback:** `V1_TTS_MAYA=false`, stop the container.
- **Decision:** keep or drop, by ear and by the QA scores. It has no speed control, so its lines are fitted
  afterwards; for Live it brings nothing over IndicF5 on timing.

## 11. Diarization (pyannote)

- **What:** who speaks when, for videos with more than one speaker (Studio HQ phase A).
- **Why deferred:** the model is gated (accept its terms, token needed) and its licence (CC-BY-4.0) asks for
  attribution; needs the QA server (item 6) started with `QA_DIARIZE=1` and `HF_TOKEN`.
- **Until then:** every line is treated as one speaker, as in v0. **Rollback:** `QA_DIARIZE=0`.

## 12. Model versions to pin on first deployment

- Model revisions are `main` in `gpu_engine_v1/docker-compose.models.yml` because only the first characters of
  the current commit hashes are known here (Maya `87a83efd`, Indic Transcribe `e083ab7d`, IndicF5 `fb652a96`).
  On the first download, read the full hash (`huggingface-cli scan-cache`) and set `TTS_REVISION`,
  `MAYA_REVISION`, `TRANSCRIBE_REVISION`, `BIG_LLM_REVISION`, and the code commits `INDICF5_COMMIT`, `MAYA_COMMIT`.
- The container images were written but never built (no Docker here).

## 13. Backup bucket

- **What:** `scripts/v1/backup.sh` copies v1's store, voice samples, trace and configuration (never keys) to a
  Cloud Storage bucket.
- **Why deferred:** no bucket exists and creating one, or signing `gcloud` in, is a cloud-console change. The
  script was syntax-checked only; with no bucket set it stops and copies nothing.
- **Commands (the user):** create a bucket, sign in on the VM (`gcloud auth login` or a service account), then
  ```bash
  V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh --dry
  V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh
  ```
  and, if wanted, a nightly line in the VM user's crontab.
- **Also the user's:** a snapshot of the VM disk in the cloud console (Step 0 of the build notes), and one
  rehearsal of the restore in `RUNBOOK.md` section 7 on another machine. Neither was done here.
- **Rollback:** nothing to roll back; a backup only adds objects to the bucket.

## 14. Prices for the cost per minute

- **What:** `/metrics-ui` shows a cost per minute only for the rates that are set: `V1_GPU_RATE_PER_HOUR`,
  `V1_STT_RATE_PER_MIN`, `V1_TTS_RATE_PER_1K_CHARS`, `V1_LLM_RATE_PER_CALL`, `V1_COST_CURRENCY`.
- **Why deferred:** the prices are the user's to give (the real hourly rate of an A100 and the hosted vendors'
  current prices). No figure was invented: all are 0, so no cost is shown.
- **Note on the GPU part:** it counts the seconds of work the model servers reported, times the hourly rate. A GPU
  that is rented by the hour costs the same when idle, so for one stream on one card the honest figure is the full
  hourly rate divided by 60 per stream minute; the counted seconds show how much of the card a stream really uses.

## 15. Decisions that are the user's

- **Indic Transcribe licence** (item 8): sign-off from its authors, or samples only.
- **Big translation model** (item 9): 12B or 31B, and which vLLM image. v0's translation server runs vLLM 0.34.0
  (read from its `/version`), which serves Gemma 4; that is the natural first choice for `VLLM_TAG`.
- **Maya 2** (item 10): keep or drop after hearing it.
- **Speaker similarity** (item 6): the model that earlier numbers used is non-commercial; the new scale has to be
  measured before a threshold means anything.
- **Which Live flags to switch on:** see `EVAL_REPORT.md`. The measured picture decides, not this list.
- **Studio HQ's translation order** when the big model is missing: the routing file says our small model first,
  then the hosted one (`studio_hq.translate`). The hosted model may translate better than the small one; swap the
  two names in `backend/config/routing.yaml` if a comparison says so.

## 16. Tunnel watchdog (`scripts\v1\tunnel-watchdog.ps1`), v1.1

- **What:** a second window beside v0's `gpu_engine\tunnel.ps1`. Every 10 s it looks at the tunnel ports
  (9001-9003, 9010, 9020, 9030, 9040) and tells four cases apart: the port answers; nothing listens (no ssh);
  ssh listens and closes at once (the server on the GPU machine is down, the tunnel is fine); ssh listens and
  nothing comes back (the link under ssh is dead). It also notes when this PC was asleep. Log:
  `data-v1\tunnel-watchdog.log`.
- **Why deferred:** it was written and not run: it may start `ssh` and, with one switch, end an `ssh.exe`; both are
  the user's to do. Its syntax was checked with PowerShell's parser, and a copy of its port check was tried on
  four local test ports (answers; hang, found after 3.0 s; closed; refused, found after 2.0 s). Whether a real
  ssh shows "closed" for a dead server and "hang" for a dead link was reasoned, not seen.
- **The choice about "restart only the tunnel":** v0's `tunnel.ps1` already restarts each ssh within 2 s of its
  exit, and ssh exits about 10 s after the link dies (`ServerAliveInterval=5`, `ServerAliveCountMax=2`). A second
  script starting ssh for the same ports would fight it. So:
  - while a `tunnel.ps1` window runs, the watchdog starts nothing and ends nothing; it reports;
  - when no `tunnel.ps1` window runs and a port has had no ssh for 20 s, it dials that group itself, with the
    same ssh options as `tunnel.ps1` (needs `-Key` and `-Target`);
  - a stuck ssh that it did not start is named in the log and left alone. Only with `-RestartStuck` does it end
    that one `ssh.exe`, after checking that this process is the one listening on the hanging port and that its
    command line forwards that port; `tunnel.ps1` then reconnects it. It never ends a PowerShell window or
    another ssh.
- **Run** (a new PowerShell window, in the v1 checkout):
  ```powershell
  # 1. report only: safe next to everything, changes nothing
  powershell -ExecutionPolicy Bypass -File scripts\v1\tunnel-watchdog.ps1
  # 2. also take over when the tunnel window is closed (the same key and target as tunnel.ps1)
  powershell -ExecutionPolicy Bypass -File scripts\v1\tunnel-watchdog.ps1 -Key C:\path\to\key -Target user@gpu-host
  # 3. also end a stuck ssh (read a day of the log from 1 or 2 first)
  powershell -ExecutionPolicy Bypass -File scripts\v1\tunnel-watchdog.ps1 -Key C:\path\to\key -Target user@gpu-host -RestartStuck
  ```
- **GPU memory:** none. **Verify:** the window prints `WATCHDOG started (...)` and then nothing while all ports
  answer; `Get-Content data-v1\tunnel-watchdog.log -Tail 20`. **Rollback:** Ctrl+C in its window (an ssh it
  started ends with it; `tunnel.ps1`'s own are untouched).

## 17. Stop the laptop sleeping on AC power, v1.1

- **What was found (read-only, Windows event log against the stream watcher's log, 24 Nov 2026):** all three
  "link stalls" of that day were this PC in Modern Standby, not the tunnel. The watcher's own lines already said
  so: the hosted services were among the 8 that did not answer.

  | Watcher: nothing answers | Windows: standby |
  |---|---|
  | 15:05:53 to 15:07:46 (2 min) | 15:05:18 to 15:07:04 |
  | 16:01:05 to 19:01:23 (3 h) | 16:01:00, sleep at 16:43:06, back at 19:00:51 |
  | 19:17:07 to 20:01:54 (44 min) | 19:17:03 to 20:01:13 |

  `powercfg /a` says this PC's standby is "S0 Low Power Idle, Network Disconnected": in standby the network is
  off, so the tunnel, the hosted services and the backend itself all stop. No breaker and no watchdog can work
  through that. Settings now (read with `powercfg /qh`): closing the lid on AC = Sleep; power button = Sleep;
  sleep after 180 min idle on AC; hibernate on AC = never.
- **Why deferred:** these change the user's Windows power settings.
- **Commands** (PowerShell or cmd; no admin needed for the current power plan):
  ```powershell
  powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0     # closing the lid on AC: do nothing
  powercfg /change standby-timeout-ac 0                                # never sleep when idle on AC
  powercfg /change hibernate-timeout-ac 0                              # never hibernate on AC (already so)
  powercfg /setactive SCHEME_CURRENT                                   # apply
  ```
  The power button and the Start menu's Sleep still put it to sleep: do not use them while a stream is live.
  On battery nothing changes (it sleeps after 3 min idle, as now): keep the charger in during a stream.
- **Verify:**
  ```powershell
  powercfg /qh SCHEME_CURRENT SUB_BUTTONS LIDACTION     # Current AC Power Setting Index: 0x00000000
  powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE  # Current AC Power Setting Index: 0x00000000
  # after a few hours: no new "entering Modern Standby" lines while on the charger
  Get-WinEvent -FilterHashtable @{LogName='System'; Id=506,507,42} -MaxEvents 10 | Format-Table TimeCreated, Id, Message -Wrap
  ```
- **GPU memory:** none. **Rollback** (the values read on 24 Nov 2026):
  ```powershell
  powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 1
  powercfg /change standby-timeout-ac 180
  powercfg /setactive SCHEME_CURRENT
  ```

## 18. The GPU's real numbers on the status page (`GET /gpu` on the VM), v1.1

- **What:** the status page used to read the card of the machine the backend runs on, which on the laptop is its
  own 6 GB card, and called it the GPU. It now says "A100 (VM): unknown" until a server on the GPU machine reports
  the card. `gpu_engine_v1/qa_server.py` has a new read-only `GET /gpu` (what `nvidia-smi` says there: memory used,
  free and total, how busy, temperature, power, memory per process). It loads nothing.
- **Why deferred:** it needs the QA server running on the VM (item 6: CPU only) and, from the laptop, one more
  forwarded port (9045), which v0's `tunnel.ps1` does not carry and which was not ours to add.
- **Commands:** item 6 on the VM, then check there: `curl -s http://127.0.0.1:9045/gpu`. From the laptop, in a
  window of its own (the same key and target as the tunnel):
  ```powershell
  ssh -i C:\path\to\key -N -o IdentitiesOnly=yes -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -o ConnectTimeout=8 -L 127.0.0.1:9045:127.0.0.1:9045 user@gpu-host
  ```
  and in v1's `backend/.env`: `V1_GPU_STATS_URL=http://127.0.0.1:9045/gpu` (this feeds the status page only;
  setting `V1_QA_URL` instead also switches the QA server's scoring in). Restart the v1 backend.
- **GPU memory:** none (the QA server runs on CPU; `/gpu` only reads `nvidia-smi`).
- **Verify:** `/health` shows the A100's free memory of 40 GB instead of "unknown";
  `curl -s http://127.0.0.1:8110/api/v1/health` has `"gpu": {"total_gb": 40.0, ...}`.
- **Rollback:** empty `V1_GPU_STATS_URL`; the page says "unknown" again.
