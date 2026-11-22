# v1 plan: files to create and change

Rule for every change in existing files: with all v1 flags off the code path is the one v0 has. New behaviour is
read from a flag (`backend/app/v1/flags.py`, values in v1's `backend/.env`).

## New files

| Path | What |
|---|---|
| `backend/app/v1/flags.py` | the v1 flags and settings, one place |
| `backend/app/v1/health.py` | `/api/v1/health`: v1 services, shared GPU servers, GPU memory |
| `backend/app/v1/trace.py` | trace per Live phrase and Studio line: JSONL + Prometheus counters |
| `backend/app/v1/metrics.py` | `/metrics` (Prometheus) and `/api/v1/metrics/summary` for the page |
| `backend/app/v1/router.py`, `backend/config/routing.yaml` | provider order per stage and mode, timeouts, fallback with reason |
| `backend/app/v1/stages.py` | `transcribe()`, `translate()`, `speak()`, `separate()`, `diarize()`, `score()` |
| `backend/app/v1/phrase.py` | dynamic phrase sizes, short-line merge, speculative translation helpers |
| `backend/app/v1/store_pg.py` | Postgres store (`V1_STORE=postgres`) |
| `backend/app/v1/queue.py` | job queue: in memory, or Redis when `REDIS_URL` is set |
| `backend/app/v1/hq/` | Studio HQ: text steps, normaliser, N-best, QA scoring, finish, phase-batched runner |
| `backend/eval/v1/` | Live and Studio eval, runs x3, report writer |
| `backend/tests/test_v1_*.py` | router, phrase logic, trace, HQ units |
| `gpu_engine_v1/` | new model servers for 9041-9045, each with `/health`, a pinned model and a stub mode |
| `docker-compose.v1.yml`, `Caddyfile.v1`, `backend/Dockerfile`, `web/Dockerfile` | project `bharatdb-v1` |
| `scripts/v1/` | start/stop, voice sample copy, `gpu-mode.sh`, backup, warm-up, demo check |
| `web/app/health/page.tsx`, `web/app/metrics-ui/page.tsx` | status page, numbers page |
| `docs/v1/` | this plan, discovery, progress, approvals, eval report, runbook, summary |

## Changed files (all behind flags or additive)

| Path | Change |
|---|---|
| `backend/app/config.py` | v1 settings (flags default off, service URLs empty) |
| `backend/app/main.py` | mounts the v1 routes |
| `backend/app/providers/__init__.py` | hands out providers through the router when it is switched on |
| `backend/app/db.py` | `get_store()` returns the Postgres store when asked for |
| `backend/app/live/pipeline.py` | trace marks; dynamic phrases, short-line merge, speculative translation, late-line shortening, back-check, each behind its flag |
| `backend/app/live/routes.py` | stock voice for sessions without a streamer (flag); per-session glossary (additive field); `played` may carry the phrase number |
| `backend/app/studio/runner.py`, `routes.py` | the HQ path when the flag is on and the job asks for it; alternates and flagged lines; trace per line |
| `backend/app/studio/stages/fit.py`, `mix.py` | speed cap as a parameter; sidechain ducking and loudness as options |
| `backend/.env.example`, `web/.env.example` | v1 keys |
| `web/app/studio/*`, `web/lib/api.ts` | HQ choice (shown when the flag is on), flagged lines and alternates in the editor |

Never changed: `gpu_engine/`, `dev.ps1`, anything under a v0 data folder.

## Order

Phases 2 to 9 as in `ARCHITECTURE.md`. After each: its checks, v0 health, commit, push, an entry in `PROGRESS.md`.
