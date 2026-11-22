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
  cd backend && V1_STORE=postgres POSTGRES_DSN=... python -m pytest tests/test_v1_store.py -q
  ```
- **Rollback:** `V1_STORE=json` (the default). The JSON file is not migrated or deleted by switching.
