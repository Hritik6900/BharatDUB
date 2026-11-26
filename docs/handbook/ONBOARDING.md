# Onboarding

From a clean Windows laptop to a running Bharat Dub, and the rules of the repository. Dated 2026-11-25.
Sources: `README.md` (Setup), `dev.ps1`, `scripts/v1/run-local.ps1`, `docs/v1/ARCHITECTURE.md` (rules),
`docs/v1/PROGRESS.md` (Setup), `docs/v1/V1_1_SUMMARY.md`.

## 1. Dev machine from zero

Requirements (`README.md`): **Python 3.11+**, **Node 20+**, **ffmpeg** (and ffprobe) on PATH, **git**. Optional:
a Supabase project (without it data stays in a local JSON file) and access to the GPU VM (without it Live and
Studio use the hosted fallbacks).

1. Clone the repository. Two working folders are used (git worktrees of one repository):

   | Folder | Branch | What | Ports |
   |---|---|---|---|
   | `Desktop\BharatDUB` | `main` | v0, the product people use; frozen at tag `v0-baseline` (`80c36d8`) | 3000, 8010 |
   | `Desktop\BharatDUB-v1` | `v1` | v1 / v1.1, all new work behind flags | 3100, 8110 |

   Create the second with `git worktree add ..\BharatDUB-v1 v1` from the v0 folder (the setup used this layout;
   the exact command used is unconfirmed).
2. Backend (in each folder that you run):
   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements.txt
   copy .env.example .env        # fill in keys yourself; never commit .env
   ```
   Demucs downloads its weights (about 80 MB) on first use.
3. Website:
   ```powershell
   cd web
   npm install
   copy .env.example .env.local  # NEXT_PUBLIC_API_BASE / NEXT_PUBLIC_WS_BASE, read at build time
   ```
4. Env files. Key names are in `backend/.env.example` and `web/.env.example`; the values come from the founder,
   never from the repository, a chat or a log. v1's `backend/.env` is its own file: set `DATA_DIR` so v1 never
   writes v0's data, and `PUBLIC_API_BASE` to the port the backend really runs on.
5. Run without keys (mock mode, v0 folder): `.\dev.ps1 -Mock`. Transcripts come from sample lines, translations
   from a phrasebook, voices are tones; Demucs, Silero, ffmpeg, the cache, live chunking and the UI run for real.
   Data goes to `backend\data-mock`. With keys: `.\dev.ps1`.
6. Run v1: `powershell -File scripts\v1\run-local.ps1` (backend 8110, website 3100). Then `scripts/v1/demo-check.sh`
   in Git Bash. More: [RUNBOOK.md](RUNBOOK.md).

## 2. Repository layout

| Path | What | Who may change it |
|---|---|---|
| `backend/app/` | FastAPI app: `providers/`, `studio/`, `live/`, `streamer/`, `shared/`; v1 code in `backend/app/v1/` | v1 branch |
| `backend/config/routing.yaml` | provider order per mode, engine and step (`V1_ROUTER`) | v1 branch |
| `backend/tests/` | pytest, fake providers, no credits | v1 branch |
| `backend/eval/`, `backend/eval/v1/` | eval harness (Live replay, Studio, STT hard set, LLM A/B) | v1 branch |
| `web/` | Next.js App Router, TypeScript, Tailwind; design rules in `FRONTEND.md` | v1 branch |
| `gpu_engine/` | v0's GPU servers (9001-9040) | **never edited from v1** |
| `gpu_engine_v1/` | v1's model servers (9041-9045), deploy kit, A/B kits | v1 branch |
| `scripts/v1/` | run, check, warm-up, watcher, comparison backends, eval, backup | v1 branch |
| `logs/` | measurements only (`logs/README.md`) | written by `scripts/v1/collect-logs.py` |
| `docs/v1/` | v1 build reports, runbook, checklist | v1 branch |
| `docs/handbook/` | this handbook | v1 branch |
| `data-v1/` | v1's store, voices, cache, eval material | git-ignored, never committed |
| `dev.ps1` | v0 dev script | **never edited from v1** |

## 3. Conventions

- **Flags default off.** Every new behaviour goes behind a `V1_*` flag in v1's `backend/.env`; tests force flags
  off; with every flag off v1 behaves as v0 ([ADR-0020](adr/0020-flags-default-off.md)). Since 26 Nov 2026 three
  things are on without a flag being set: `V1_HQ_ADAPTIVE` (HQ jobs only), the review of every HQ job, and the
  viewer hold's way back (kill switch `LIVE_SYNC_EASE`); tests still force `V1_HQ_ADAPTIVE` off.
- **Never touch v0.** No start, stop, restart or reconfigure of 3000, 8010, 9001-9003, 9010, 9020, 9030, 9040. v1
  only calls the shared GPU servers. Never read or write v0's data (`backend/data`, `backend/data-mock`, its
  JSON, its voice folders) ([ADR-0018](adr/0018-v1-beside-v0.md)).
- **No test session on v0.** A session on 8010 is a session in the product people use. Measure with comparison
  backends (`scripts\v1\ab-server.ps1 -Port 812x`); start them from PowerShell so stopping the task stops the
  server, and stop them afterwards (NEEDS_APPROVAL item 18).
- **One run at a time.** One GPU through one tunnel is one stream; the hosted account takes one request at a time.
  Check nobody is live before a replay.
- **GPU memory:** a new model only if free minus need stays at least 4 GB; never touch CUDA MPS.
- **Commits** ([ADR-0023](adr/0023-repo-hygiene.md)):
  - no media, zips, model weights or files over 10 MB;
  - no mention of an AI assistant or its vendor anywhere: files, comments, docs, commit messages, trailers, PR text;
    the local rules file and the local tool settings stay git-ignored;
  - the `pre-commit` and `commit-msg` hooks (installed for the v1 worktree) enforce this; **never use
    `--no-verify`**;
  - no secrets: `.env`, `*.env` are git-ignored (only `*.env.example` is tracked);
  - commit after each working step with a clear message; reference ADR or EXP ids, e.g.
    `router: circuit breaker (ADR-0027)`.

## 4. Tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
```

Offline, fake providers, no credits. At the end of v1.1: **311 pass, 1 skipped** (the Postgres store test, no
database) (`docs/v1/V1_1_SUMMARY.md`, 25 Nov 2026). After v1.2 Part 1: **336 pass, 1 skipped** (26 Nov 2026,
`docs/v1/PROGRESS.md`). Real provider checks: `python -m scripts.smoke` (costs
credits).

## 5. Eval

| What | How | Source |
|---|---|---|
| Whole v1 eval, one thing at a time | `scripts/v1/eval-all.sh <eval data folder> <out folder>` (Live v1 flags-off, Studio standard vs HQ, STT key words on the hard set) | `scripts/v1/eval-all.sh` |
| Live replay of a recording across settings | `python -m eval.live_replay <file> --out <dir> --target a=http://127.0.0.1:8120 --target b=... --runs 5` | `../v1/RUNBOOK.md` section 3 |
| Live first 10 phrases | `python -m eval.live_first <dir>` | `docs/v1/PROGRESS.md` WS2 |
| Studio table | `python -m eval.v1.studio_table <out> --ab <data>/ab` | `../v1/RUNBOOK.md` |
| Rescore old Studio jobs without a voice call | `python -m eval.v1.rescore --data <DATA_DIR> --jobs <ids> --out <dir>` | same |
| Translation A/B (12B) | `python -m eval.v1.llm_ab run / sheet / verdict` | NEEDS_APPROVAL item 9 |
| v0's results file | `python -m eval.run` rebuilds `backend/eval/results.csv` | `README.md` |

Eval material (the dense reel, class videos, the hard set audio) is in `data-v1\eval\`, not in git. Read the
numbers in [RESULTS.md](RESULTS.md); two equal Live runs differ by about 10 points in timing and 6 in words heard
back (SPEC section 17), so one run proves little.

## 6. Documentation rules

| Change | Write |
|---|---|
| Behaviour change | a line under **Unreleased** in `CHANGELOG.md` |
| A design choice | an ADR in `docs/handbook/adr/` ([adr/README.md](adr/README.md)) |
| A measurement | an EXP in `docs/handbook/experiments/` and its numbers in [RESULTS.md](RESULTS.md) |
| A new term | [GLOSSARY.md](GLOSSARY.md) |
| An outage or a data mistake | [INCIDENTS.md](INCIDENTS.md) |

- Before each push: `powershell -File scripts\docs\gen-docs.ps1` (rewrites only the generated sections: ADR and EXP
  indexes, commit history, results tables).
- `python scripts/docs/docs-check.py` is a manual check (links, ids, forbidden words), not a hook.
- Every number: source, date, conditions, n and spread, and **measured / estimate / target / stand-in**. No
  transcripts, translations, audio or video ids in docs or logs.
