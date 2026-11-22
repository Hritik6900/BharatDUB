# v1 runbook

How to start, stop, check and roll back v1. v0 keeps running the whole time: nothing here stops or changes it,
except the HQ window (section 5), which pauses v0's small translation model and is run by hand.

Ports: v1 website 3100, v1 backend 8110, new model servers 9041-9045. v0: 3000, 8010, 9001-9040 (never bound,
only called).

## 1. Start and stop

**Without containers** (what was used to build and test v1):

```bash
cd /srv/bharatdb-v1/app
cp backend/.env.example backend/.env        # once: keys, DATA_DIR=/srv/bharatdb-v1/data, CORS_ORIGINS, PUBLIC_API_BASE
scripts/v1/run-local.sh                      # backend 127.0.0.1:8110, website 127.0.0.1:3100; logs in .run-v1/
scripts/v1/stop-local.sh                     # stops those two processes and nothing else
```

On Windows: `powershell -File scripts\v1\run-local.ps1`.

**With Docker** (written, never run: see `NEEDS_APPROVAL.md` items 2-4):

```bash
cp .env.v1.example .env.v1                   # ports, data folder, public address
docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 up -d --build
docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 --profile https up -d   # with a domain
docker compose -p bharatdb-v1 -f docker-compose.v1.yml down
```

Every service has `restart: always` and a health check, so after a VM restart the containers come back by
themselves. v0's model servers do not: start them with v0's own scripts (`start_live.sh`, `start_sep.sh`,
`start_llm.sh`, `start_stt.sh` in its engine folder), then run the warm-up below.

From a laptop, reach the site through SSH forwards of 3100 and 8110 (`ssh -L 3100:127.0.0.1:3100 -L
8110:127.0.0.1:8110 ...`), unless the HTTPS profile is up. A browser gives the microphone only to `localhost` or an
HTTPS page.

## 2. Check

```bash
scripts/v1/demo-check.sh          # READY / NOT READY: backend, website, every model server, hosted services, GPU, flags
scripts/v1/warmup.sh              # one small request through each service; prints each time
scripts/v1/v0-check.sh            # v0 is still fine (read-only)
scripts/v1/gpu-mode.sh status     # which model servers answer, free GPU memory, who is live
```

Pages: `/health` (green or red per service, GPU memory, flags that are on) and `/metrics-ui` (numbers from the
trace). Endpoints: `GET /api/v1/health`, `/api/v1/flags`, `/api/v1/routing`, `/api/v1/metrics/summary?hours=24`,
`/metrics` (Prometheus), `POST /api/v1/warmup`.

**Before a demo:** 15 minutes ahead run `demo-check.sh` and `warmup.sh`; the card must be in normal mode (not an HQ
window) and no other session live. One GPU through one address is one stream.

## 3. Flags

All in v1's `backend/.env`, all off by default; with every flag off v1 behaves as v0. Restart the backend after a
change. What each one does, and what was measured, is in `PROGRESS.md` and `EVAL_REPORT.md`.

| Flag | On | Roll back |
|---|---|---|
| `V1_TRACE` | a record per Live phrase and Studio line; `/metrics-ui` fills | off: only logging stops |
| `V1_ROUTER` | providers from `backend/config/routing.yaml` | off: v0's fixed table |
| `V1_PHRASE_DYNAMIC` | first phrase 4-6 words, later 8-12, lines under 3 words join the next | off: 6-12 words |
| `V1_SPEC_TRANSLATE` | a paused speaker's words are translated ahead of the final | off |
| `V1_LLM_PREFIX_CACHE` | our translation model: fixed rules first, temperature 0.1 | off |
| `V1_LIVE_LATE_SHORTEN` | a late line is said shorter instead of skipped | off: skipped as v0 |
| `V1_LIVE_BACKCHECK` | a dubbed live line is heard back by the QA server, made again if wrong | off |
| `V1_LIVE_STOCK_DEFAULT` | a Live session without a streamer profile speaks in stock voices | off: consent tick as v0 |
| `V1_TTS_SERVER` | copied voice from `V1_TTS_SERVER_URL` (:9041) | off: 9001-9003 |
| `V1_TTS_MAYA` | Maya 2 as a candidate voice in Studio HQ | off |
| `V1_STUDIO_HQ` | the HQ choice on `/studio` and `quality=hq` on a job | off: every job is standard |
| `V1_FIT_115` | Studio speeds a line up by at most 1.15x, then shortens | off: 1.35x |
| `V1_STORE` | `postgres` (with `POSTGRES_DSN`) | `json` |

Not a flag but a setting: `LIVE_FIT_MAX_TEMPO=1.2` caps the Live speed-up at 1.2x (v0: 1.3).

To compare a flag on and off on the same machine, start a second backend on another port with only that flag:
`scripts/v1/ab-server.sh 8112 dynamic V1_PHRASE_DYNAMIC=true`, then
`python -m eval.v1.live <video> --out <dir> --target base=http://127.0.0.1:8111 --target dynamic=http://127.0.0.1:8112`.

## 4. Routing

`backend/config/routing.yaml` lists, per mode (`live`, `studio`, `studio_hq`), engine and step, the providers in
order. A provider whose address or key is not set is skipped. `GET /api/v1/routing` shows what is configured and
what is in use now. Add a model server by starting it and setting its address in `backend/.env`
(`V1_QA_URL`, `V1_TRANSCRIBE_URL`, `V1_BIG_LLM_URL`, `V1_TTS_SERVER_URL`, `V1_MAYA_URL`).

## 5. The GPU's two modes

Normal: v0's servers as they are (about 34 of 40 GB). HQ window: the small translation model on 9020 is stopped
and a larger one runs on 9044 (and Indic Transcribe on 9043) for Studio HQ.

```bash
scripts/v1/gpu-mode.sh hq               # prints what it would do
scripts/v1/gpu-mode.sh hq --run         # refuses while a session is live
scripts/v1/gpu-mode.sh normal --run     # back; starts 9020 with v0's own start script
```

During the window v0 and v1 Live translate through the hosted model by themselves. Run it at night or when nobody
is live. Every switch is written to `<data>/gpu-mode.log`.

HQ jobs for a window: create them with `hold=true` (they wait), open the window, then
`curl -X POST http://127.0.0.1:8110/api/v1/hq/batch -H 'content-type: application/json' -d '{}'`. The batch does
the audio work of every job, then the text work of every job (the big model is used once), then the voices.

## 6. Roll back to v0

v0 was never changed, so rolling back is using v0's address again: website 3000, backend 8010.

- One behaviour misbehaves: switch its flag off and restart the v1 backend.
- v1 as a whole misbehaves: `scripts/v1/stop-local.sh` (or `docker compose ... down`). Nothing in v0 depends on v1.
- The code: tag `v0-baseline` (commit `80c36d8`) is v0 as it was before v1.
- The card is stuck in an HQ window: `scripts/v1/gpu-mode.sh normal --run`; if 9020 still does not answer, run
  v0's `start_llm.sh` in its engine folder. Until then v0 translates through the hosted model.

## 7. Backup and restore on a new GPU machine

```bash
V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh --dry    # what would be copied
V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh
```

Copied: the store, voice samples, the trace, the routing and compose files, the names (not the values) of the
settings. Not copied: keys, the cache, uploads and renders. Needs a bucket and a signed-in `gcloud`
(`NEEDS_APPROVAL.md`).

Restore on a fresh machine with an NVIDIA GPU:

1. v0's model servers: v0's engine folder and its `setup_machine.sh`, `setup_gpu_mode.sh` and start scripts
   (models download again from Hugging Face; IndicF5 is gated, sign in first).
2. `git clone` the repository to `/srv/bharatdb-v1/app`, `git checkout v1`.
3. Copy the backup's store and `voices/` into `/srv/bharatdb-v1/data/`; write `backend/.env` from
   `backend/.env.example` (the keys come from wherever they are kept, not from the backup).
4. `scripts/v1/run-local.sh`, then `scripts/v1/demo-check.sh` and `scripts/v1/warmup.sh`.

This restore has not been rehearsed. A VM disk snapshot (taken in the cloud console) is the faster way back and
is the user's to take.
