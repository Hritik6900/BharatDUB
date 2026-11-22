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
