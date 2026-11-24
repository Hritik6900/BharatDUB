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

None of these was run with its real model on the GPU: the card has about 6 GB free beside v0 and the rule is to
keep 4 GB free, and the build ran on a laptop. The stub mode of each was run, and the QA server's speaker model was
run on the laptop's CPU (25 Nov 2026, `docs/v1/MODELS.md`). The batched path of `tts_server.py`, and the
model calls in `maya_server.py` and `transcribe_server.py`, were written from the libraries' documented
interfaces; expect to fix details on the first real start.

## Deploy kit (`deploy/`): three commands a server, no Docker, no sudo

Copy this folder to the GPU machine, start one server, test it:

```bash
scp -r gpu_engine_v1 <user>@<gpu machine>:~/                         # 1. copy
ssh <user>@<gpu machine> "bash ~/gpu_engine_v1/deploy/start.sh qa"   # 2. build its environment, check the card, start
ssh <user>@<gpu machine> "bash ~/gpu_engine_v1/deploy/smoke.sh qa"   # 3. PASS or FAIL, timing, GPU memory taken
```

Servers: `qa` (9045, CPU), `tts` (9041), `maya` (9042), `transcribe` (9043), `big-llm` (9044; `--size 12b` or
`31b`). `deploy/stop.sh <server>` ends it; `deploy/status.sh` shows what answers. All four are thin wrappers of
`deploy/kit.py` (Python 3.8+, no packages), which:

- reads `nvidia-smi` first and refuses to start unless free memory minus the server's need is at least 4 GB
  (needs: qa 0, tts 4, maya 9.2, transcribe 10, big-llm 14 for 12B and 27 for 31B; estimates and the model
  cards' figures, none measured: after the first real start give the measured figure with `--need-gb`);
- binds only 9041-9045 and refuses when the port already answers; it never touches 9001-9003, 9010, 9020,
  9030, 9040, and never starts, stops or configures CUDA MPS (it only says whether MPS is running);
- writes `run/<server>.pid`, `run/<server>.json` (free memory before the start) and `run/<server>.log`;
  `stop` ends only the process in its own pid file, after checking that it is still that server;
- builds one Python environment per server under `.venvs/` (`--python PATH` uses an existing interpreter
  instead; `--dry-run` prints every command; `--stub` starts the server without its model).

The big translation model is started with the `vllm` program v0's translation server was installed with
(`~/voice_engine/.venv_llm/bin/vllm`, only run, never changed; `VLLM_BIN` names another).

Tested here (`backend/tests/test_v1_ws5.py`): the memory rule against a stand-in `nvidia-smi`, the refusals,
start, smoke and stop of a stub server on a free port, the smoke client against fake servers. NOT tested: any
start with a real model, and the kit on Linux (it was written and run on Windows; the process-group and `/proc`
parts run only there).

## A/B kits

- `ab/maya_ab.py` + `ab/voice_lines.tsv`: 20 fixed lines (6 English) through IndicF5 (:9001) and Maya 2 (:9042)
  in one voice taken from a profile with consent; two folders of same-named wav files and `pairs/pairs.json`
  for the blind listening page.
- `backend/eval/v1/llm_ab.py`: 40 fixed lines into three languages through two translation models, a blind
  side-by-side sheet, and a verdict by a rule fixed beforehand.

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
