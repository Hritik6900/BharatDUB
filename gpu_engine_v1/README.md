# v1 model servers (ports 9041-9045)

New servers for v1. v0's servers (`gpu_engine/`, ports 9001-9040) are not changed by anything here.
Models, licences and sizes: `docs/v1/MODELS.md`. What still needs a decision or the GPU: `docs/v1/NEEDS_APPROVAL.md`.

| Port | File | What | Calls |
|---|---|---|---|
| 9041 | `tts_server.py` | one IndicF5 that batches lines | `POST /ref`, `POST /tts`, `GET /health` (as v0's engines) |
| 9042 | `maya_server.py` | Maya 2 Native | the same three calls |
| 9043 | `transcribe_server.py` | Indic Transcribe | `POST /stt`, `GET /health` |
| 9044 | (vLLM image) | a larger Gemma 4, 4-bit | OpenAI-compatible `/v1` |
| 9045 | `qa_server.py` | hear a line back, speaker similarity, diarization | `POST /score`, `POST /diarize`, `GET /health` |

Every server listens on 127.0.0.1 only, has `/health`, reads its model name and revision from the environment,
and has a **stub mode** (`V1_STUB=1`): it starts without its model and without a GPU and answers with
well-formed made-up results, so the backend's calls can be tested before a model is allowed onto the card.

## Status

None of these was run with its real model: the card has about 6 GB free beside v0 and the rule is to keep 4 GB
free, and the build ran on a laptop. The stub mode of each was run. The batched path of `tts_server.py`, and the
model calls in `maya_server.py` and `transcribe_server.py`, were written from the libraries' documented
interfaces; expect to fix details on the first real start.

## Start

Stub mode, no Docker (any machine with Python):

```bash
cd gpu_engine_v1 && pip install fastapi "uvicorn[standard]" python-multipart numpy soundfile
V1_STUB=1 uvicorn qa_server:app --host 127.0.0.1 --port 9045
```

With Docker on the VM (one profile per server; see the top of `docker-compose.models.yml`):

```bash
docker compose -p bharatdb-v1-models -f gpu_engine_v1/docker-compose.models.yml --profile qa up -d --build
```

Then set the server's address in v1's `backend/.env` (`V1_QA_URL=http://127.0.0.1:9045` and so on). The router
(`backend/config/routing.yaml`) picks a server up as soon as its address is set and skips it while it is not.

The big translation model runs only inside an HQ window: `scripts/v1/gpu-mode.sh hq --run` stops the small model
on 9020 and starts the big one; `scripts/v1/gpu-mode.sh normal --run` reverses it. Without `--run` the script
prints what it would do.

## Versions

Image tags and Python packages are fixed in the Dockerfiles. Model revisions are `main` until the first
deployment: set `TTS_REVISION`, `MAYA_REVISION`, `TRANSCRIBE_REVISION` and `BIG_LLM_REVISION` to the full commit
hash that was downloaded, and `VLLM_TAG` to the vLLM release used.
