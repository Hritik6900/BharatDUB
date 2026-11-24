# ADR-0033: GPU model servers via a no-Docker, no-sudo deploy kit that refuses unless 4 GB stays free

- **Status:** accepted (not yet run)
- **Date:** 2026-11-25
- **Superseded by:** —

## Context

v0's servers hold about 34 of 40 GB on the A100 and need headroom for spikes (`../../v1/ARCHITECTURE.md` rule 6).
CUDA MPS runs on the machine and must not be touched (`../../v1/NEEDS_APPROVAL.md`, "Three rules"). The v1 build
rules forbid sudo and system packages (rule 8). Whether the VM has Docker is not known (`../../v1/DISCOVERY.md`
risk 7). The v1 GPU-mode script starts the big model as a container: `gpu-mode.sh hq --run` without Docker would
stop v0's translation server on 9020 and then fail before its own way back (`../../v1/PROGRESS.md` v1.1 WS5).

## Options considered

| Option | Outcome |
|---|---|
| Docker Compose per server (`docker-compose.models.yml`, phase 6) | written, never run; needs Docker and likely sudo (item 3, optional) |
| `gpu-mode.sh hq` / `normal` | on the do-not-run list; unsafe without Docker (above) |
| A small Python kit: one venv per server, start / smoke / stop / status, memory check first | **chosen** |

## Decision

`gpu_engine_v1/deploy/` (`kit.py`, Python 3.8+, no packages; wrappers `start.sh`, `smoke.sh`, `stop.sh`,
`status.sh`):

- A server is three commands: copy the folder, `start.sh <server>`, `smoke.sh <server>`.
- `start` reads `nvidia-smi` and refuses unless free minus need >= 4 GB, before and after building the environment;
  refuses if the port already answers; only knows ports 9041-9045; says whether MPS runs and never touches it.
- `smoke` prints PASS/FAIL per check, its time, and the GPU memory the server holds; `stop` ends only the process in
  the kit's own pid file after checking its command line.
- Needs in the table (GB, **estimates** from cards and weights, none measured): qa 0, tts 4, maya 9.2,
  transcribe 10, big-llm 14 (12B) / 27 (31B). `--need-gb` takes a measured figure.

## Consequences

### Good

- Cannot by itself push v0 out of GPU memory or stop v0's servers; tested on Windows with a stand-in `nvidia-smi`
  and stub servers (24 tests in `tests/test_v1_ws5.py`).
- The QA server runs on CPU with no GPU memory (ADR-0025).

### Bad

- Never run on Linux or on the VM; the process-group and `/proc` parts were read, not run.
- With about 6 GB free, the 4 GB rule allows nothing above 2 GB beside v0: every GPU server waits for an HQ window
  that stops v0's translation model for a while (`../../v1/MODELS.md`; ADR-0026).
- 31B does not fit by the estimates (about 24 GB in a window; 27 + 4 = 31).
- The 12B checkpoint may not start on v0's vLLM 0.34.0: its first start is a test in itself.

## Evidence

- Commits: `ddb8d59` (branch `v1-ws5`), merged as `df27b93`; `bb71d9a` (servers and compose file, phase 6)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) v1.1 WS5 and phase 6; [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md)
  "Three rules" and items 4, 8-11; [`MODELS.md`](../../v1/MODELS.md) WS5 section;
  [`gpu_engine_v1/README.md`](../../../gpu_engine_v1/README.md); [`ARCHITECTURE.md`](../../v1/ARCHITECTURE.md) rules 6-8
