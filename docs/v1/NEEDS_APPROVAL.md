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
