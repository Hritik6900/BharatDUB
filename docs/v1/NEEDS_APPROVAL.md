# v1: what waits for you, as one checklist

Work from the top. Every item says what it is, why it waits, the exact commands, what it does to the GPU's memory,
how to see that it worked and how to undo it. Nothing in this list was run by the build: it needs the GPU machine,
a command the build was not allowed to use, or your decision.

**Who does what**

| Mark | Meaning |
|---|---|
| **VM** | commands on the GPU machine (through `ssh`), written out below |
| **LAPTOP** | commands on this PC only |
| **YOU** | a decision, a recording, a label or a price: no command does it for you |

**Where things are.** Commands are for PowerShell in the v1 checkout (`C:\Users\hriti\Desktop\BharatDUB-v1`)
unless an item says otherwise. The key is the file `C:\Users\hriti\Downloads\test4-ocr_ssh_key`, the machine is
`ocr@34.47.88.232`. Inside a quoted remote command never write a `$`: PowerShell would replace it.

**Three rules for every VM item**

1. **The card first.** Before anything new is loaded:
   ```powershell
   ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv"
   ```
   A server may start only when **free - needed >= 4 GB**. The deploy kit (`gpu_engine_v1/deploy/`) reads
   `nvidia-smi` itself and refuses otherwise; the "Card" line of each item gives the numbers.
2. **CUDA MPS is running on the machine: never touch it.** No item starts, stops or configures it. The kit only
   says whether it runs. (The new servers run outside MPS, the way v0's translation model does.)
3. **v0's servers are not touched** (9001-9003 voice, 9010 separation, 9020 translation, 9030 speech-to-text,
   9040 second voice), with one exception that is always marked: an **HQ window** stops the translation model on
   9020 for a while (part C). The kit binds only 9041-9045 and stops only what it started (its own pid file).

**The deploy kit in one look** (items 4, 8, 9, 10, 11 use it; `gpu_engine_v1/README.md`):

```powershell
scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes -r gpu_engine_v1 ocr@34.47.88.232:~/
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/start.sh <server>"
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/smoke.sh <server>"
```

`<server>` is `qa`, `tts`, `maya`, `transcribe` or `big-llm`. `start.sh` builds the server's own Python environment
on the first run (minutes; the model downloads on the first start), `smoke.sh` prints PASS or FAIL for each check,
the time each took and the GPU memory the server holds. `stop.sh <server>` ends it; `status.sh` shows everything.
The kit was tested on this PC with a stand-in `nvidia-smi` and stub servers; **no server has been started with its
real model yet, and the kit has not run on Linux**: read what `start.sh` prints the first time.

To reach the new servers from the laptop (the A/B kits and the status page need it), one more window, beside v0's
tunnel and not touching it:

```powershell
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -N -o IdentitiesOnly=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -L 127.0.0.1:9041:127.0.0.1:9041 -L 127.0.0.1:9042:127.0.0.1:9042 -L 127.0.0.1:9043:127.0.0.1:9043 -L 127.0.0.1:9044:127.0.0.1:9044 -L 127.0.0.1:9045:127.0.0.1:9045 ocr@34.47.88.232
```

Other documents written before 25 Nov 2026 cite the old item numbers: the table at the end translates them.
Items 16-18 take five minutes, need no VM and can be done at any time.
Added after the checklist was ordered, at the end of this file: item 27 (documentation), item 28
(**Get written confirmation of commercial use from AI4Bharat / legal review**: it is about the voice model the
product runs on today, so read it before any contract) and item 29 (**auto mode on `/live`: three decisions from
the v1.2 measurement**; one line in a file each, no VM: read it before the next stream on v1).

---

# Part A. Move the v1 backend to the GPU machine

Why this is first: every Live phrase now crosses the tunnel several times (speech-to-text, translation, voice).
With the backend beside the engines only the sound and the finished dub cross it. v0 measured this once, in its
all-GPU mode (SPEC.md section 21, one run each): first audio p50 2.3 s through the tunnel, 1.8 s with the backend on
the machine. v1 has not been measured there.

## 1. Look at the machine (VM, read-only) (was item 1)

- **What:** the processes behind 9001-9003, 9010, 9020, 9030, 9040, their folders, the GPU memory each holds, and
  whether the machine has what items 2-11 need (Python with `venv`, ffmpeg, git, Docker, CPU cores, disk).
- **Why it waits:** the build ran on the laptop and was not to open a shell on the machine. Every memory figure in
  this file is an estimate until this is run.
- **Commands:**
  ```powershell
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "ss -ltnp | grep -E ':(900[1-3]|9010|9020|9021|9030|9040|904[1-5]|8110) '; ps -eo pid,etimes,cmd | grep -E 'voice_engine|sep_engine|stt_engine|vllm|mio_engine|mps-control' | grep -v grep"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "python3 --version; python3 -m venv --help > /dev/null && echo venv-ok; which ffmpeg ffprobe git docker node; nproc; free -g | head -2; df -h ~ | tail -1"
  ```
- **Card:** nothing is loaded. **MPS:** running, never touch it (the second command shows it; that is all).
- **Verify:** three answers. Write the per-process memory into `DISCOVERY.md` section 6 and, where a figure
  differs from this file's estimates, use the measured one (`start.sh <server> --need-gb <measured>`).
- **Roll back:** nothing to roll back.
- **Known so far:** the engines were installed under `~/voice_engine` for user `ocr`. If `venv-ok` is missing,
  the kit and item 2 cannot build environments: give them an existing interpreter (`--python`, item 4 says how).

## 2. Start the v1 backend on the machine (VM + LAPTOP) (was item 3)

- **What:** the v1 backend (port 8110) runs on the GPU machine; the website stays on the laptop (port 3100) and
  reaches it through one forwarded port. Nothing of v0 moves.
- **Why it waits:** needs a shell on the machine. No `sudo`: everything goes under `~/bharatdb-v1`.
- **Commands** (the laptop's v1 backend keeps running until step 5):
  ```powershell
  # 1. the code as one file (no git sign-in needed on the machine), and the folder for it
  git archive --format=tar -o data-v1\v1.tar v1
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes data-v1\v1.tar ocr@34.47.88.232:~/
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "mkdir -p ~/bharatdb-v1/app ~/bharatdb-v1/data && tar -xf ~/v1.tar -C ~/bharatdb-v1/app"
  # 2. the settings with the keys (the file is copied, never shown), and your recorded voices
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes backend\.env ocr@34.47.88.232:~/bharatdb-v1/app/backend/.env
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes -r data-v1\voices data-v1\local_db.json ocr@34.47.88.232:~/bharatdb-v1/data/
  # 3. look, then start (the first start builds the Python environment: several minutes)
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/bharatdb-v1/app/scripts/v1/vm-backend.sh --check"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/bharatdb-v1/app/scripts/v1/vm-backend.sh"
  # 4. on the laptop: stop the laptop's v1 backend (Ctrl+C in its window; the website on 3100 stays)
  # 5. forward the backend's port, in a window of its own
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -N -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -L 127.0.0.1:8110:127.0.0.1:8110 ocr@34.47.88.232
  ```
  `vm-backend.sh` sets the data folder and the ffmpeg paths in the copied `.env` for the machine (the laptop's file
  names Windows paths), starts the backend alone (`V1_SKIP_WEB=1 scripts/v1/run-local.sh`) and waits until it
  answers. It was syntax-checked and never run.
- **Card:** the backend takes no GPU memory (its own fallbacks for separation and voice detection run on CPU).
  **MPS:** running, never touch it; the script does not.
- **Verify:** in Git Bash on the laptop `scripts/v1/demo-check.sh` says READY and `scripts/v1/v0-check.sh` says v0
  answers; `http://localhost:3100/health` is green; one Live session on `/live`. Then measure: the same run as
  `EVAL_REPORT.md` section 1, once more.
- **Roll back:** close the forward's window;
  `ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/bharatdb-v1/app/scripts/v1/stop-local.sh"`;
  start the laptop's backend again (`powershell -File scripts\v1\run-local.ps1`). The laptop's data was only copied.
- **Know before you start:** jobs in the copied store name files on the laptop and will not open there; voices and
  streamer profiles carry over. Sessions made on the machine are not in the laptop's store afterwards. A newer
  version of the code is the same first three lines again, then `stop-local.sh` and `vm-backend.sh`.
  If ffmpeg is missing on the machine, Live works and Studio does not: say so and it goes into this list.

## 3. Docker on the machine (VM, optional) (was item 2)

- **What:** `docker-compose.v1.yml` and `gpu_engine_v1/docker-compose.models.yml` need Docker Engine with the
  compose plugin and, for GPU containers, the NVIDIA container toolkit.
- **Why it waits:** installing them needs `sudo`. **Nothing else in this list needs Docker any more**: the backend
  starts with item 2 and the model servers with the deploy kit. Docker is only for HTTPS with Caddy (item 13) and
  Postgres (item 14).
- **Commands (check first; item 1 already says whether `docker` is there):**
  ```powershell
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "docker --version && docker compose version; docker info | grep -i -E 'runtimes|nvidia'"
  ```
  If missing: Docker's own install guide for the machine's distribution, then `sudo usermod -aG docker ocr`, then
  the NVIDIA container toolkit guide. These are yours to run.
- **Card:** none. **MPS:** running, never touch it (installing the container toolkit restarts nothing of ours,
  but do it when nobody is live).
- **Verify:** the command above prints versions. **Roll back:** `docker compose -p bharatdb-v1 -f docker-compose.v1.yml down`.

---

# Part B. On the machine, no GPU memory

## 4. QA server on the machine's CPU (:9045) (VM) (was item 6)

- **What:** `gpu_engine_v1/qa_server.py` with its real models on CPU: Whisper large-v3-turbo (hears a dubbed line
  back in any of our languages) and a speaker model (how close the copied voice is to the speaker). It gives
  Studio HQ its speaker-similarity score, a back-check that does not use the hosted one-request account, the scorer
  of the live back-check, the second judge (item 6) and the card's numbers for the status page (item 5).
- **Why it waits:** needs a shell on the machine and about 2 GB of model downloads.
- **Licences (checked on the models' own pages, `MODELS.md`):** Whisper through faster-whisper MIT; the speaker
  model `speechbrain/spkrec-ecapa-voxceleb` Apache-2.0, open to commercial use. The server loads only a speaker
  model that is listed as checked; the one earlier numbers used (ECAPA2, non-commercial) is refused.
- **Commands:**
  ```powershell
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes -r gpu_engine_v1 ocr@34.47.88.232:~/
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/start.sh qa"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/smoke.sh qa"
  ```
  Then in the v1 backend's `backend/.env` (on the machine after item 2; on the laptop with the forward of the
  intro): `V1_QA_URL=http://127.0.0.1:9045`, and restart the backend.
- **Card:** needs 0 GB: the kit starts it with no CUDA device visible, so it cannot take GPU memory. The kit still
  reads `nvidia-smi` and refuses when under 4 GB is free (nothing new on a card that full). **MPS:** running,
  never touch it.
- **Verify:** `smoke.sh qa` ends with `RESULT: PASS (4 of 4 checks ...)`; its `health` line says `device=cpu` and
  `speaker=speechbrain/spkrec-ecapa-voxceleb (Apache-2.0)`; its `GPU memory` line says the server's processes hold
  0.0 GB.
- **Roll back:** `ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/stop.sh qa"`;
  empty `V1_QA_URL`. Scoring falls back to the hosted speech-to-text (words only).
- **If the first start fails on the environment:** `start.sh qa --python <an interpreter that has the packages>`
  skips building one. With Docker (item 3) the old way still works:
  `docker compose -p bharatdb-v1-models -f gpu_engine_v1/docker-compose.models.yml --profile qa up -d --build`.
- **Not measured:** the Whisper on the machine's CPU (how long a line takes to hear back), and what the server's
  four CPU threads (`QA_THREADS`) do to a Live session running at the same time. Score a Studio job once while
  nobody is live and read `score_ms_avg` in `curl -s http://127.0.0.1:9045/health`.
- **Then (a decision inside, YOU):** the speaker scores are on a new scale. Measured on the laptop's CPU, one run:
  two cuts of the eval reel's speaker 0.88 (7 s each) and 0.77 (3 s each), another voice 0.14. That is one
  speaker, not a baseline: before `V1_HQ_SIMILARITY_MIN` is set, score your own recorded voice against itself and
  against its copies (`POST /similarity` with two files).

## 5. The card's real numbers on the status page (VM + LAPTOP) (was item 18)

- **What:** the status page says "A100 (VM): unknown" until a server on the machine reports the card. The QA
  server's read-only `GET /gpu` does (memory used, free and total, how busy, temperature, power, memory per
  process). It loads nothing.
- **Why it waits:** needs item 4.
- **Commands:** item 4, then check: `ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "curl -s http://127.0.0.1:9045/gpu"`.
  In the v1 backend's `backend/.env`: `V1_GPU_STATS_URL=http://127.0.0.1:9045/gpu` (this feeds the status page
  only; `V1_QA_URL` of item 4 also does it). Restart the backend. With the backend still on the laptop, the forward
  of the intro must be open.
- **Card:** none (`/gpu` only reads `nvidia-smi`). **MPS:** running, never touch it.
- **Verify:** `/health` shows the A100's free memory of 40 GB instead of "unknown";
  `curl -s http://127.0.0.1:8110/api/v1/health` has `"gpu": {"total_gb": 40.0, ...}`.
- **Roll back:** empty `V1_GPU_STATS_URL`; the page says "unknown" again.

## 6. A second judge for Tamil, Bengali and the other languages (VM) (was item 22)

- **What:** with `V1_HQ_JUDGE` the heard-back judge is the hosted speech-to-text first and a Whisper next. The
  Whisper on 9030 is a Hindi and Hinglish model, so it is a second judge for Hindi lines only. For every other
  language the second judge is the QA server's multilingual Whisper. The backend side is built and tested with a
  fake server: once `V1_QA_URL` is set, `qa_server` is in the judge order after the other two
  (`V1_HQ_JUDGE_ORDER=prisma,whisper_gpu,qa_server`). Until then a take the hosted judge cannot score is stored as
  "not checked".
- **Why it waits:** needs item 4.
- **Commands:** item 4, then in the v1 backend's `backend/.env`: `V1_QA_URL=http://127.0.0.1:9045`, `V1_HQ_JUDGE=true`.
- **Card:** none (item 4 is on CPU). **MPS:** running, never touch it.
- **Verify:** `GET /api/v1/jobs/<id>/backcheck?lang=ta-IN` on a finished job shows `judges` (who scored how many
  lines). To see the second judge work, run one job with `V1_HQ_JUDGE_BY_LANG=ta-IN=qa_server` and compare its
  scores with the hosted judge's on the same job (`python -m eval.v1.rescore --hear-all`).
- **Roll back:** empty `V1_QA_URL`.
- **Before trusting it:** how the QA server's Whisper scores against the hosted judge on the same takes has not
  been measured (it has never run with its real model). Two judges' scores are not comparable until it has.

## 7. Who speaks when: diarization (VM + YOU) (was item 11)

- **What:** pyannote's `speaker-diarization-community-1` for videos with more than one speaker (Studio HQ phase A).
- **Why it waits:** the model is gated: someone has to accept its terms on Hugging Face (they share contact
  details) and give the token; its licence (CC-BY-4.0) asks for attribution. Needs item 4.
- **Commands** (after accepting the terms; the token is typed on the machine, never into a file in the repository):
  ```powershell
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/stop.sh qa"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "~/gpu_engine_v1/.venvs/qa/bin/python -m pip install 'pyannote.audio>=4.0'"
  ssh -t -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "read -s -p 'Hugging Face token: ' HF_TOKEN; export HF_TOKEN; QA_DIARIZE=1 bash ~/gpu_engine_v1/deploy/start.sh qa"
  ```
  The last line asks for the token on the machine (it is not shown and not stored) and hands it to the server's
  process only.
- **Card:** none (CPU). **MPS:** running, never touch it.
- **Verify:** `smoke.sh qa` passes; `curl -s http://127.0.0.1:9045/health` on the machine says `"diarization": true`.
- **Roll back:** `stop.sh qa`, then `start.sh qa` without `QA_DIARIZE`. Until then every line is treated as one
  speaker, as in v0.

---

# Part C. On the machine, with GPU memory

By the estimates v0's servers hold about 34 of the card's 40 GB, so about 6 GB is free and nothing in this part
fits beside them (item 1 gives the real figures). Each item therefore runs inside an **HQ window**.

**The HQ window (VM; the one place where a v0 server is stopped, by you).** The small translation model on 9020 is
stopped; v0 and v1 Live then translate through the hosted model by themselves until it is back. Do it when nobody
is live.

```powershell
# is anybody live? (both must print nothing)
curl.exe -s http://127.0.0.1:8010/api/live/sessions | Select-String -SimpleMatch '"status":"live"'
curl.exe -s http://127.0.0.1:8110/api/live/sessions | Select-String -SimpleMatch '"status":"live"'
# OPEN: look at the process, stop that one, see the memory come back (about 10 s)
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "pgrep -af 'vllm serve google/gemma-4-E4B-i[t]'"
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "pkill -f 'vllm serve google/gemma-4-E4B-i[t]'"
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv"
# ... the item's own commands ...
# CLOSE: first stop every server of this part that the kit started, then v0's own start script
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/stop.sh big-llm; bash ~/gpu_engine_v1/deploy/stop.sh maya; bash ~/gpu_engine_v1/deploy/stop.sh transcribe; bash ~/gpu_engine_v1/deploy/stop.sh tts"
ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/voice_engine/start_llm.sh"
curl.exe -s http://127.0.0.1:9020/v1/models      # answers again after a minute or two
```

- `[t]` in the pattern keeps `pkill` from matching the command that carries it. The pattern is the one v0's own
  `start_llm.sh` uses; it does not match the 12B or 31B model.
- v0's start script gives the small model half the card while it starts (about 20 GB): it comes back only when
  the kit's GPU servers are stopped first.
- **MPS is running: never touch it.** Neither opening nor closing the window does.
- With Docker on the machine (item 3) `scripts/v1/gpu-mode.sh hq --run` and `normal --run` do the same switch and
  start the big model as a container; without Docker do not use it (it would stop 9020 and then fail to start
  anything). Either way every switch is your command.
- Estimated free memory inside a window: about 24 GB (40 less the voice engines' 12, separation 1.4 and
  speech-to-text 2.5; not measured).

## 8. Maya 2 (:9042) and the voice A/B (VM + LAPTOP + YOU) (was item 10)

- **What:** a second voice that also copies a voice **in English**, which IndicF5 cannot (it has no English; today
  English lines go to the hosted copy or a stock voice). The kit speaks 20 fixed lines (6 English, 4 Hindi,
  4 Tamil, 3 Bengali, 3 Punjabi: `gpu_engine_v1/ab/voice_lines.tsv`) with IndicF5 on 9001 and with Maya 2 in the
  same recorded voice, and builds the blind pairs for the listening page `/listen-test`.
- **Why it waits:** GPU memory (below), and Maya's server was written from its model card's example and has never
  run: expect to fix details on the first start. The A/B needs Maya on the machine.
- **Card:** needs 9.2 GB (the card's figure for loading; 7.7 GB steady), so **free must be at least 13.2 GB**:
  only inside an HQ window. **MPS:** running, never touch it.
- **Commands:**
  ```powershell
  # OPEN the HQ window (above), then:
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes -r gpu_engine_v1 ocr@34.47.88.232:~/
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/start.sh maya"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/smoke.sh maya"
  # the A/B, from the laptop (the forward of the intro must be open; 9001 comes through v0's tunnel):
  backend\.venv\Scripts\python.exe gpu_engine_v1\ab\maya_ab.py --store data-v1\local_db.json --voice <voice profile id> --out data-v1\eval\maya_ab
  # afterwards: stop it and CLOSE the window
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/stop.sh maya"
  ```
  `<voice profile id>`: the id of a voice **recorded with consent** in v1 (`curl.exe -s http://127.0.0.1:8110/api/voices`
  lists them). The kit takes the voice only from a profile with consent on record and has no other way in. It
  refuses while a stream is live. It sends 40 lines in all and leaves one extra voice entry on the 9001 engine
  until that engine is next restarted.
- **Out:** `data-v1\eval\maya_ab\indicf5\<id>.wav` and `maya\<id>.wav` (the same names), `pairs\<id>_a.wav`,
  `<id>_b.wav` and `pairs\pairs.json` (`pairs: [{id, lang, text, a, b, a_system, b_system}]`; which system is A
  changes from pair to pair), `timing.json`. **The listening page's own builder script is the final word on the
  format**: if it wants another shape, feed it the two folders; `--pairs-only` rebuilds `pairs\` without speaking.
  For the six English lines IndicF5 is sent the line as it is; the pair is marked "IndicF5 was not trained on this
  language", and a line it refuses is listed under `missing`.
- **Verify:** `smoke.sh maya` ends with `RESULT: PASS (5 of 5 checks ...)` (Hindi, Tamil and English lines) and
  prints the memory Maya holds: note it. The A/B prints the time to make a line for each system and the number of
  pairs.
- **Roll back:** `stop.sh maya`; `V1_TTS_MAYA=false` (the default). Close the window.
- **Decision (YOU):** keep or drop, by ear on `/listen-test` and by the QA scores. To use it in Studio HQ:
  `V1_MAYA_URL=http://127.0.0.1:9042`, `V1_TTS_MAYA=true`. It has no speed control, so its lines are fitted
  afterwards; for Live it brings nothing over IndicF5 on timing. Its 9.2 GB do not fit beside v0 outside a window.

## 9. Big translation model (:9044): 12B first, 31B only if 12B wins (VM + LAPTOP + YOU) (was item 9)

- **What:** `google/gemma-4-12B-it-qat-w4a16-ct` (Google's own 4-bit checkpoint for vLLM; Apache-2.0, not gated,
  one 10.3 GB file: checked on its page, `MODELS.md`) against the small model on 9020, on 40 fixed lines into
  Tamil, Bengali and Punjabi, with a blind sheet for you and a rule for "wins" that was fixed before any result:
  1. you preferred the 12B line in at least 60% of the pairs you decided, on at least 40 decided pairs;
  2. in no language under 50% (at least 10 decided pairs each);
  3. no more lines in a wrong script or with Latin letters than the small model, and no empty line;
  4. its lines are not longer: median letters 12B / small at most 1.10;
  5. fast enough for Studio: median at most 2.0 s a line in batches of 8.
  Beside it the script says whether it would be fast enough for Live (median at most 0.6 s, 95th percentile at
  most 1.0 s a phrase).
- **Why it waits:** GPU memory, and stopping a v0 server is yours to do. Also unknown: whether the vLLM that v0's
  server runs (0.34.0) starts this checkpoint. Its page's discussion reports start failures on earlier builds; one
  cause was fixed in the checkpoint itself, the other has no confirmed fix (`MODELS.md`). `smoke.sh` tells.
- **Card:** the kit gives vLLM 14 GB (weights 10.3 GB plus its cache; an estimate), so **free must be at least
  18 GB**: only inside an HQ window. **MPS:** running, never touch it.
- **Commands:**
  ```powershell
  # BEFORE the window, while 9020 is up: the small model's lines (laptop, in backend\)
  cd backend
  .venv\Scripts\python.exe -m eval.v1.llm_ab run --name current --url http://127.0.0.1:9020/v1 --model local --out ..\data-v1\eval\llm_ab
  .venv\Scripts\python.exe -m eval.v1.llm_ab run --name current-live --mode live --url http://127.0.0.1:9020/v1 --model local --out ..\data-v1\eval\llm_ab
  cd ..
  # OPEN the HQ window (above), then:
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes -r gpu_engine_v1 ocr@34.47.88.232:~/
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/start.sh big-llm"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/smoke.sh big-llm"
  # the 12B model's lines (laptop; the forward of the intro must be open)
  cd backend
  .venv\Scripts\python.exe -m eval.v1.llm_ab run --name big12 --url http://127.0.0.1:9044/v1 --model big --out ..\data-v1\eval\llm_ab
  .venv\Scripts\python.exe -m eval.v1.llm_ab run --name big12-live --mode live --url http://127.0.0.1:9044/v1 --model big --out ..\data-v1\eval\llm_ab
  # stop it and CLOSE the window, then the sheet
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/stop.sh big-llm"
  .venv\Scripts\python.exe -m eval.v1.llm_ab sheet --a current --b big12 --out ..\data-v1\eval\llm_ab
  # YOU: open data-v1\eval\llm_ab\side_by_side.csv, fill the `better` column with X, Y or same, save, then
  .venv\Scripts\python.exe -m eval.v1.llm_ab verdict --a current --b big12 --out ..\data-v1\eval\llm_ab
  ```
  The model downloads on the first start (10.3 GB to `~/bharatdb-v1-models`; `start.sh` waits up to 30 minutes).
  Each `run` sends 120 lines and waits while a stream is live.
- **Verify:** `smoke.sh big-llm` ends with `RESULT: PASS (2 of 2 checks ...)` and prints the memory the server
  holds: note it (afterwards `start.sh big-llm --need-gb <measured>`). `verdict` prints each check and
  `VERDICT: big12 WINS over current`, `DOES NOT WIN`, or `NOT DECIDED` (too few votes).
- **Roll back:** `stop.sh big-llm`, close the window. If 9020 does not come back, v0 and v1 keep translating
  through the hosted model; run `bash ~/voice_engine/start_llm.sh` again and read `~/voice_engine/llm.log`.
- **If 12B wins:** `V1_BIG_LLM_URL=http://127.0.0.1:9044/v1` in the v1 backend's `.env` for Studio HQ jobs run
  inside a window (create them with `hold=true`, open the window, then `POST /api/v1/hq/batch`, `RUNBOOK.md`
  section 5).
- **31B, only then:** `start.sh big-llm --size 31b` (the kit gives it 27 GB: weights 23.3 GB plus cache, so free
  must be at least 31 GB) and the same A/B with `--name big31`, compared with `--a big12 --b big31`. **By the
  estimates it does not fit:** a window leaves about 24 GB free. It would need the voice engines stopped as well
  (no Live and no Studio voice meanwhile) or a second card. That is a decision, not a deploy.
- **Also yours:** Studio HQ's translation order when the big model is missing: the routing file says our small
  model first, then the hosted one (`studio_hq.translate` in `backend/config/routing.yaml`); swap the two names if
  a comparison says the hosted one translates better.

## 10. Voice server with batching (:9041), `V1_TTS_SERVER` (VM) (was item 7)

- **What:** one IndicF5 process that batches lines, to replace v0's three processes (about 12 GB) for v1.
- **Why it waits:** GPU memory, and the batched path has never run (written from the library's interface): it must
  be compared with v0's audio first.
- **Card:** needs about 4 GB (an estimate from v0's engines), so **free must be at least 8 GB**: inside an HQ
  window, or whenever item 1 shows that much free. **MPS:** running, never touch it.
- **Commands:**
  ```powershell
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes -r gpu_engine_v1 ocr@34.47.88.232:~/
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/start.sh tts"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/smoke.sh tts"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "curl -s http://127.0.0.1:9041/health"
  ```
  IndicF5 is gated on Hugging Face: the machine's account already downloaded it for v0. If the kit's own
  environment cannot be built, v0's has everything: `start.sh tts --python ~/voice_engine/.venv2/bin/python`
  (the interpreter is only run, nothing in it is changed).
- **Verify:** `smoke.sh tts` ends with `RESULT: PASS (4 of 4 checks ...)` and prints the memory held. In `/health`:
  `batching: true`, `batch_errors: 0`, and under load `largest_batch` at least 2. Compare the same sample and line
  through 9001 and 9041 by ear. Then in the v1 backend's `.env`: `V1_TTS_SERVER_URL=http://127.0.0.1:9041`,
  `V1_TTS_SERVER=true`.
- **Roll back:** `V1_TTS_SERVER=false` (v1 goes back to 9001-9003 at once), then `stop.sh tts`.

## 11. Indic Transcribe (:9043) (VM + YOU) (was item 8)

- **What:** a second speech-to-text for Studio HQ (two hearings, merged by the translation model).
- **Why it waits:** (a) GPU memory; (b) **licence, YOU:** hosting it as a service others call needs its authors'
  written sign-off (`MODELS.md`); (c) the model is gated: its terms must be accepted on Hugging Face by the account
  whose token is used.
- **Card:** needs about 10 GB (9.2 GiB by its card), so **free must be at least 14 GB**: only inside an HQ window.
  **MPS:** running, never touch it.
- **Commands (inside an HQ window, after the licence decision):**
  ```powershell
  scp -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes -r gpu_engine_v1 ocr@34.47.88.232:~/
  ssh -t -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "read -s -p 'Hugging Face token: ' HF_TOKEN; export HF_TOKEN; bash ~/gpu_engine_v1/deploy/start.sh transcribe"
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "bash ~/gpu_engine_v1/deploy/smoke.sh transcribe"
  ```
  then `V1_TRANSCRIBE_URL=http://127.0.0.1:9043` in the v1 backend's `.env`.
- **Verify:** `smoke.sh transcribe` ends with `RESULT: PASS (2 of 2 checks ...)` and prints the memory held.
- **Roll back:** `stop.sh transcribe`, empty `V1_TRANSCRIBE_URL`; HQ then hears with the hosted speech-to-text only.

## 12. Pin the model versions after the first downloads (VM) (was item 12)

- **What:** model revisions are `main` in the kit and in `gpu_engine_v1/docker-compose.models.yml`. After a
  server's first good start, fix what was downloaded so a later start cannot get another version.
- **Commands:**
  ```powershell
  ssh -i C:\Users\hriti\Downloads\test4-ocr_ssh_key -o IdentitiesOnly=yes ocr@34.47.88.232 "ls ~/bharatdb-v1-models/hf/hub/*/snapshots/"
  ```
  The folder names are the full commit hashes. Start with them from then on, for example
  `BIG_LLM_REVISION=<hash> bash ~/gpu_engine_v1/deploy/start.sh big-llm` (also `TTS_REVISION`, `MAYA_REVISION`,
  `TRANSCRIBE_REVISION`, and the code commits `INDICF5_COMMIT`, `MAYA_COMMIT`). Seen on the pages on 25 Nov 2026:
  12B `1d2c2d7f2466070e69d6fb3fd5ce9a7d75f2f6ee`, the speaker model `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`;
  earlier, first characters only: Maya `87a83efd`, Indic Transcribe `e083ab7d`, IndicF5 `fb652a96`.
- **Card:** none. **MPS:** running, never touch it. **Roll back:** leave the variable out (`main` again).
- The container images were written but never built (no Docker here).

---

# Part D. Hosting, later

## 13. Domain, HTTPS and the demo password (VM + YOU) (was item 4)

- **What:** the `https` profile of `docker-compose.v1.yml` (Caddy) needs a domain whose DNS points at the machine,
  ports 80 and 443 open in its firewall, and a password hash.
- **Why it waits:** DNS, firewall and cloud console changes are yours; needs Docker (item 3).
- **Commands (on the machine, in the checkout):**
  ```bash
  docker run --rm caddy:2.8-alpine caddy hash-password --plaintext '<the demo password>'
  # in .env.v1: V1_DOMAIN=<domain>  V1_DEMO_PASSWORD_HASH='<hash>'
  #             V1_PUBLIC_ORIGIN=https://<domain>  V1_PUBLIC_WS_ORIGIN=wss://<domain>
  docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 --profile https up -d --build
  ```
- **Note:** a browser gives the microphone only to an HTTPS page or to `localhost`. Until there is a domain, the
  site works through the forwards (item 2).
- **Card:** none. **MPS:** running, never touch it. **Roll back:** `docker compose ... --profile https down`.

## 14. Postgres store (`V1_STORE=postgres`) (VM) (was item 5)

- **What:** `backend/app/v1/store_pg.py` keeps the store's rows in Postgres.
- **Why it waits:** there was no database to run it against, so it has never been executed. Treat it as untested.
  Needs Docker (item 3) or a Postgres of your own.
- **Commands (on the machine, in the checkout):**
  ```bash
  docker compose -p bharatdb-v1 -f docker-compose.v1.yml --env-file .env.v1 --profile postgres up -d postgres
  # backend/.env: V1_STORE=postgres  POSTGRES_DSN=postgresql://bharatdb:<password>@127.0.0.1:5440/bharatdb
  cd backend && TEST_POSTGRES_DSN=postgresql://bharatdb:<password>@127.0.0.1:5440/bharatdb python -m pytest tests/test_v1_store.py -q
  ```
- **Card:** none. **MPS:** running, never touch it.
- **Roll back:** `V1_STORE=json` (the default). The JSON file is not migrated or deleted by switching.

## 15. Backup bucket (VM + YOU) (was item 13)

- **What:** `scripts/v1/backup.sh` copies v1's store, voice samples, trace and configuration (never keys) to a
  Cloud Storage bucket.
- **Why it waits:** no bucket exists and creating one, or signing `gcloud` in, is a cloud-console change. The
  script was syntax-checked only; with no bucket set it stops and copies nothing.
- **Commands:** create a bucket, sign in on the machine (`gcloud auth login` or a service account), then there:
  ```bash
  V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh --dry
  V1_BACKUP_BUCKET=gs://<bucket>/bharatdb-v1 scripts/v1/backup.sh
  ```
  and, if wanted, a nightly line in the machine user's crontab.
- **Also yours:** a snapshot of the machine's disk in the cloud console, and one rehearsal of the restore in
  `RUNBOOK.md` section 7 on another machine. Neither was done.
- **Card:** none. **MPS:** running, never touch it. **Roll back:** nothing; a backup only adds objects to the bucket.

---

# Part E. On the laptop only

## 16. Stop the laptop sleeping on AC power (LAPTOP) (was item 17)

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
- **Why it waits:** these change your Windows power settings.
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
- **Card:** not involved. **Roll back** (the values read on 24 Nov 2026):
  ```powershell
  powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 1
  powercfg /change standby-timeout-ac 180
  powercfg /setactive SCHEME_CURRENT
  ```
- After item 2 the backend no longer sleeps with the laptop, but the sound still comes from the laptop's browser:
  this item stays worth doing.

## 17. Tunnel watchdog (`scripts\v1\tunnel-watchdog.ps1`) (LAPTOP) (was item 16)

- **What:** a second window beside v0's `gpu_engine\tunnel.ps1`. Every 10 s it looks at the tunnel ports
  (9001-9003, 9010, 9020, 9030, 9040) and tells four cases apart: the port answers; nothing listens (no ssh);
  ssh listens and closes at once (the server on the GPU machine is down, the tunnel is fine); ssh listens and
  nothing comes back (the link under ssh is dead). It also notes when this PC was asleep. Log:
  `data-v1\tunnel-watchdog.log`.
- **Why it waits:** it was written and not run: it may start `ssh` and, with one switch, end an `ssh.exe`; both are
  yours to do. Its syntax was checked with PowerShell's parser, and a copy of its port check was tried on
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
- **Commands** (a new PowerShell window, in the v1 checkout):
  ```powershell
  # 1. report only: safe next to everything, changes nothing
  powershell -ExecutionPolicy Bypass -File scripts\v1\tunnel-watchdog.ps1
  # 2. also take over when the tunnel window is closed (the same key and target as tunnel.ps1)
  powershell -ExecutionPolicy Bypass -File scripts\v1\tunnel-watchdog.ps1 -Key C:\Users\hriti\Downloads\test4-ocr_ssh_key -Target ocr@34.47.88.232
  # 3. also end a stuck ssh (read a day of the log from 1 or 2 first)
  powershell -ExecutionPolicy Bypass -File scripts\v1\tunnel-watchdog.ps1 -Key C:\Users\hriti\Downloads\test4-ocr_ssh_key -Target ocr@34.47.88.232 -RestartStuck
  ```
- **Card:** not involved. **Verify:** the window prints `WATCHDOG started (...)` and then nothing while all ports
  answer; `Get-Content data-v1\tunnel-watchdog.log -Tail 20`. **Roll back:** Ctrl+C in its window (an ssh it
  started ends with it; `tunnel.ps1`'s own are untouched).

## 18. Five comparison backends left running on ports 8111-8115 (LAPTOP) (was item 24)

- **What:** five v1 comparison backends started for the Studio measurement on 25 Nov 2026 are still running,
  idle: 8111 (`ws3-std`), 8112 (`ws3-hq`), 8113 (`ws3-fixed`), 8114 (`ws3-adapt`), 8115 (`ws3-new`). They hold
  those ports, some memory, and nothing else: no job is running on them, and they are not v0, the v1 backend on
  8110, a model server or the tunnel.
- **Why it waits:** they were started through Git Bash, where stopping the task ends the shell around the
  server and leaves the server. Ending a process by its id was not among the things the build was allowed to do.
- **Commands (PowerShell on the laptop):**
  ```powershell
  Get-NetTCPConnection -LocalPort 8111,8112,8113,8114,8115 -State Listen | Select-Object LocalPort, OwningProcess
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match '--port 811[1-5]' } |
      Select-Object ProcessId, CommandLine        # check: only the five comparison backends
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match '--port 811[1-5]' } |
      ForEach-Object { Stop-Process -Id $_.ProcessId }
  ```
- **Card:** not involved.
- **Verify:** `curl http://127.0.0.1:8111/health` (and 8112-8115) no longer answers; `scripts/v1/v0-check.sh` still
  says v0 answers; `http://127.0.0.1:8110/api/v1/health` still answers.
- **Roll back:** nothing to undo. From now on comparison backends are started with `scripts\v1\ab-server.ps1` from
  PowerShell, where stopping the task stops the server (checked on 8116-8118 in the same work).

## 19. What the session-start measurement could not cover (LAPTOP + YOU) (was item 21)

- **v1.2 note:** `V1_LIVE_WARMSTART` was removed with its code in v1.2 Part 2 (ADR-0037), so part (a) of this item
  and its off/on steps no longer apply; the male-speaker and stock-voice parts stand without the flag.
- **What:** (a) Streamer Mode with a recorded voice: `V1_LIVE_WARMSTART` sends the stored voice to the engines when
  the session is created and speaks one short line per language on every engine process; tested with a fake
  engine only. (b) A male speaker: the eight male stock voices answer on the hosted service, but no session with
  a male voice was run, and nobody has heard whether the matched voice is the better one. (c) The English voices
  on a night the hosted stock voice is healthy: the stock voice's timing in `PROGRESS.md` is from a night it
  refused 59% of its lines.
- **Why it waits:** (a) a comparison backend has an empty store, and a voice has to be recorded in v1 with consent
  (v0's consent records are not copied; `scripts/v1/copy-voice-samples.sh` says why); your recorded voice was
  not used for a test you did not ask for. (b) needs a recording of a male speaker that is yours to dub. (c) needs
  another night and about 15 minutes of hosted calls.
- **Commands (laptop only, no VM):** record the voice on `http://localhost:3100/streamer` (v1), note the
  streamer's id, then with `V1_LIVE_WARMSTART` off and on in v1's `backend\.env` (restart the v1 backend between):
  ```powershell
  cd backend
  .venv\Scripts\python.exe -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\ws2\streamer-off `
      --target v1=http://127.0.0.1:8110 --busy http://127.0.0.1:8010 --runs 5 --loops 2 --langs pa-IN,ta-IN --streamer <id>
  .venv\Scripts\python.exe -m eval.live_first ..\data-v1\eval\ws2\streamer-off --data v1=..\data-v1
  ```
  (the same again into `streamer-on` with the flag on). For (b): the same two commands as in `PROGRESS.md`
  (v1.1 WS2, "test by hand") on a recording of a male speaker; `warm.speaker` in the session's `/metrics` should
  say `male` and `warm.stock_voice` name Zayan (Punjabi), Dhruva (Bengali), Pranav (English); Tamil and Telugu
  stay female and say so. For (c): the three-backend run of `PROGRESS.md` once more.
- **Card:** nothing new is loaded (the engines that already run).
- **Verify:** `first.md` in each folder: first audio p50 / p95 of the first 10 phrases, lines in a stock voice
  (with a recorded voice: 0 expected in both).
- **Roll back:** nothing to undo.

---

# Part F. Yours: recordings, labels, choices, prices

## 20. Two or three dense recordings of your own for the Live replay (YOU + LAPTOP) (was item 19)

- **What:** 2-3 recordings of about 10 minutes each, your own content (or content you have the right to dub),
  where the speaker talks almost without a pause: a class, a commentary, a rant. Any file ffmpeg reads (mp4, mkv,
  m4a, wav). Put them in `data-v1\eval\dense\` (the folder is not in the repository; nothing in it is committed).
- **Why it waits:** Live audio is never stored, so no real stream can be replayed. The only dense material on this
  machine is one 24.9 s reel; `docs/v1/LIVE_DENSE_REPORT.md` is measured on that reel played eight times in a
  row, which repeats the same 11-12 phrases and says nothing about a speaker who changes pace or topic over ten
  minutes. The densest long sessions in the logs (62% speaking over 16 minutes on 24 Nov) left only their numbers.
- **Commands (laptop only, no VM, no sudo; costs hosted speech-to-text for the minutes replayed):**
  ```powershell
  # two comparison backends, each in its own window (they stop with Ctrl+C)
  powershell -File scripts\v1\ab-server.ps1 -Port 8111 -Name m-off    -Flags "LIVE_SYNC_ADAPT=false"
  # v1.2: V1_LIVE_RATECTRL no longer exists; the controller runs in auto mode only: -Mode auto instead of the flags
  powershell -File scripts\v1\ab-server.ps1 -Port 8113 -Name m-ctl    -Mode auto -Flags "LIVE_SYNC_ADAPT=false" -Overrides "live_stock_default=off"
  cd backend
  .venv\Scripts\python.exe -m eval.live_replay ..\data-v1\eval\dense\<file> --out ..\data-v1\eval\ws1\<name> `
      --target off=http://127.0.0.1:8111 --target ctl=http://127.0.0.1:8113 --runs 3 --langs pa-IN,ta-IN
  ```
  The harness waits while a stream is live on 8010 or 8110 and skips the run if it is still live after 30 minutes.
  (Ports 8111 and 8113 are free only after item 18.)
- **Card:** nothing new is loaded.
- **Verify:** `data-v1\eval\ws1\<name>\summary.md` has one column per setting; `speaking share` in it says how
  dense the recording really is.
- **Roll back:** nothing to undo; stop the comparison backends.

## 21. Labels for the calibration page (YOU) (was item 23)

- **What:** `/studio/calibrate` needs a person who speaks the language to label takes good or bad: at least 30 per
  language with 5 of each kind before a flag line is recommended (`CALIBRATION.md`). Until then
  `V1_HQ_BACKCHECK_MIN=0.9` is the value v1 started with, not a measured one, and "flagged lines" is a count
  nobody has checked by ear.
- **Why it waits:** it needs ears, for Tamil and Bengali a speaker of each.
- **Commands (laptop only):** `V1_HQ_CALIBRATE=true` and `V1_HQ_JUDGE=true` in v1's `backend\.env`, restart the
  backend, open `http://localhost:3100/studio/calibrate`. The takes of the three test videos are there once
  `python -m eval.v1.rescore --data ..\data-v1 --jobs a69b4e0b,7782d82a,6bb779d8 --out ..\data-v1\eval\ws3\rescore --write-hearings`
  has run (done in the WS3 work; it reads the cache only).
- **Card:** not involved.
- **Roll back:** `V1_HQ_CALIBRATE=false`; delete `data-v1\calibration\labels.jsonl` to start over.

## 22. The English voice, and what a session does when the stock voice fails (YOU + LAPTOP) (was item 20)

- **What:** two decisions. (a) `V1_EN_VOICE` for `V1_EN_SINGLE_VOICE`: `auto` takes the one stock voice, because
  every line in the hosted copy was 13 points worse on time on the dense reel (`PROGRESS.md`, v1.1 WS2); `copy`
  keeps your own voice in English at that cost, with one change of voice after the opening when the voice is
  learned from the stream. (b) Whether a session in the stock voice should move once to the copy, and stay there,
  when the stock voice stops answering. It does not today: on 25 Nov the hosted stock voice refused 59% of its
  lines and `auto` left 42% of the English lines without audio, while the copy answered all of its lines.
  Item 8 may change this choice: Maya 2 would be a third English voice, your own, made on our card.
- **Why it waits:** (a) is a matter of which you would rather hear; nobody has listened. (b) changes a voice in
  mid-session, which is what the flag exists to stop; it needs your yes.
- **Commands (laptop only, no VM; costs hosted calls for the minutes spoken):**
  ```powershell
  powershell -File scripts\v1\ab-server.ps1 -Port 8112 -Name en-copy  -Flags "V1_EN_SINGLE_VOICE=true,V1_EN_VOICE=copy"
  powershell -File scripts\v1\ab-server.ps1 -Port 8113 -Name en-stock -Flags "V1_EN_SINGLE_VOICE=true,V1_EN_VOICE=stock"
  cd backend
  .venv\Scripts\python.exe -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\ws2\hear `
      --target copy=http://127.0.0.1:8112 --target stock=http://127.0.0.1:8113 --runs 1 --loops 8 --langs en-IN,pa-IN --keep-audio
  ```
  `--keep-audio` writes one WAV per dubbed line into `data-v1\eval\ws2\hear\runs\<setting>_r1\`; play the `en-IN_*.wav`
  files in order. To live with one of them: `V1_EN_SINGLE_VOICE=true` and `V1_EN_VOICE=copy` or `stock` in v1's
  `backend\.env`, restart the v1 backend. (Ports 8112 and 8113 are free only after item 18.)
- **Card:** nothing new is loaded.
- **Verify:** `GET /api/live/sessions/<id>/metrics` has `"en_voice": "copy"` or `"stock"`;
  `python -m eval.live_first ..\data-v1\eval\ws2\hear --data copy=..\data-v1\ab\en-copy --data stock=..\data-v1\ab\en-stock --lang en-IN`
  shows "changes of voice" 1 and 0.
- **Roll back:** `V1_EN_SINGLE_VOICE=false` and restart; English is chosen line by line again.

## 23. Prices for the cost per minute (YOU) (was item 14)

- **What:** `/metrics-ui` shows a cost per minute only for the rates that are set: `V1_GPU_RATE_PER_HOUR`,
  `V1_STT_RATE_PER_MIN`, `V1_TTS_RATE_PER_1K_CHARS`, `V1_LLM_RATE_PER_CALL`, `V1_COST_CURRENCY`.
- **Why it waits:** the prices are yours to give (the real hourly rate of an A100 and the hosted vendors'
  current prices). No figure was invented: all are 0, so no cost is shown.
- **Note on the GPU part:** it counts the seconds of work the model servers reported, times the hourly rate. A GPU
  that is rented by the hour costs the same when idle, so for one stream on one card the honest figure is the full
  hourly rate divided by 60 per stream minute; the counted seconds show how much of the card a stream really uses.
- **Card:** not involved. **Roll back:** set the rates to 0.

## 24. The decisions in one place (YOU) (was item 15)

- **Indic Transcribe licence** (item 11): sign-off from its authors, or samples only.
- **Big translation model** (item 9): 12B if it wins by the rule; 31B does not fit beside the voice engines by the
  estimates. Which vLLM: v0's translation server runs 0.34.0 (read from its `/version`) and the kit runs that
  one; whether it starts the 12B checkpoint is not known until `smoke.sh` has run.
- **Maya 2** (item 8): keep or drop after hearing it; whether English in your own voice from it replaces today's
  English choice (item 22).
- **Speaker similarity** (item 4): the model earlier numbers used is non-commercial and is refused now; the new
  scale has to be measured on your voice before a threshold means anything.
- **The speaker model's training data:** its licence is Apache-2.0, but it was trained on VoxCeleb, whose own page
  states no licence (`MODELS.md`). If that matters for a contract, it is a question for a lawyer, not for this list.
- **Which Live flags to switch on:** see `EVAL_REPORT.md`. The measured picture decides, not this list.
- **Studio HQ's translation order** when the big model is missing (item 9, last line).

## 25. A pitch video of a real stream, and how long recordings are kept (YOU + LAPTOP) (was item 25)

- **What:** the side-by-side video in `data-v1\pitch\` is the test reel played three times by the replay harness.
  A video for a pitch should be a real stream or a real video of the speaker's own, recorded from the console.
- **Why deferred:** it needs the speaker's agreement to keep their dubbed voice, and the flag switched on on the
  backend people use (8110, restarted).
- **Decided and built on 26 Nov 2026 (v1.2 Part 1):** recording stays opt-in (the flag and the session's own
  tick); a recording is deleted by itself 30 days after it ended (`V1_RECORD_KEEP_DAYS=30`; checked when the
  backend starts and every half hour); any recording can be deleted at once from the list on `/live` or with
  `DELETE /api/v1/recordings/<session>`. The backend on 8110 gets this when it is next restarted.
- **Still yours to decide:** deleting a voice profile does not delete recordings spoken in it. It cannot today:
  a recording does not say whose voice it holds. No rule was given, so none was built.
- **Commands (PowerShell, v1 checkout):**
  ```powershell
  # backend\.env: V1_LIVE_RECORD=true (and V1_LIVE_BUDGET=true if wanted), then restart the v1 backend
  # /live: tick "Keep a recording of this session's dub on this server", feed the video from this page, stop
  powershell -File scripts\v1\render-pitch.ps1 -Recording data-v1\recordings\<session> -Video C:\path\the-video.mp4 `
      -Lang pa-IN -Stereo split -Out data-v1\pitch\<name>.mp4
  # afterwards, if the recording should not stay: the Delete button in the list on /live, or
  curl.exe -X DELETE http://127.0.0.1:8110/api/v1/recordings/<session>
  # what is kept, and the day each one goes by itself:
  curl.exe http://127.0.0.1:8110/api/v1/recordings
  ```
- **GPU memory:** none beyond the session itself.
- **Verify:** the script prints the numbers it wrote on the picture; play the file with headphones (left ear the
  original, right ear the dub).
- **Rollback:** `V1_LIVE_RECORD=false`, restart; delete `data-v1\recordings\` and `data-v1\pitch\`. A video
  rendered into `data-v1\pitch\` is not a recording and is not deleted by the 30-day rule: delete it by hand.
- **Decide:** whether deleting a voice should delete the recordings made with it. (How long a recording may
  stay is decided: 30 days; another number is `V1_RECORD_KEEP_DAYS` in `backend\.env`, `0` = never by itself.)

## 26. Listeners for the blind listening test (YOU) (was item 26)

- **What:** `/listen-test` is built and empty. It needs pairs (item 8 makes them: IndicF5 against Maya 2, same lines)
  and people who speak the language to rate them.
- **Why deferred:** no pairs exist yet, and who listens is yours to ask.
- **Commands:**
  ```powershell
  backend\.venv\Scripts\python.exe scripts\v1\make-listen-pairs.py <folder of system A> <folder of system B> `
      --system-a indicf5 --system-b <name> --lang ta-IN --name "<what this set is>"
  # backend\.env: V1_LISTEN_TEST=true, restart the backend; send listeners http://<host>:3100/listen-test
  ```
- **GPU memory:** none.
- **Verify:** `/metrics-ui` shows the listening block: "No ratings yet", then per system the mean rating, the
  number of ratings and the preference share. About 20 pairs a language and five listeners is a start; fewer
  says little.
- **Rollback:** `V1_LISTEN_TEST=false`; move `data-v1\listen\results.jsonl` away to start again.

---

## Old number, new number

| Was | Now | What | Kind |
|---|---|---|---|
| 1 | 1 | look at the machine | VM |
| 2 | 3 | Docker | VM, optional |
| 3 | 2 | the v1 backend on the machine | VM + LAPTOP |
| 4 | 13 | domain, HTTPS, demo password | VM + YOU |
| 5 | 14 | Postgres store | VM |
| 6 | 4 | QA server on CPU | VM |
| 7 | 10 | voice server with batching | VM |
| 8 | 11 | Indic Transcribe | VM + YOU |
| 9 | 9 | big translation model, HQ window | VM + LAPTOP + YOU |
| 10 | 8 | Maya 2 and the voice A/B | VM + LAPTOP + YOU |
| 11 | 7 | diarization | VM + YOU |
| 12 | 12 | pin model versions | VM |
| 13 | 15 | backup bucket | VM + YOU |
| 14 | 23 | prices | YOU |
| 15 | 24 | the decisions in one place | YOU |
| 16 | 17 | tunnel watchdog | LAPTOP |
| 17 | 16 | stop the laptop sleeping | LAPTOP |
| 18 | 5 | the card's numbers on the status page | VM + LAPTOP |
| 19 | 20 | dense recordings | YOU + LAPTOP |
| 20 | 22 | the English voice | YOU + LAPTOP |
| 21 | 19 | session-start measurement, the rest | LAPTOP + YOU |
| 22 | 6 | second judge | VM |
| 23 | 21 | labels for calibration | YOU |
| 24 | 18 | five leftover comparison backends | LAPTOP |
| 25 | 25 | a pitch video of a real stream, how long recordings stay (30 days, built 26 Nov 2026; the voice-profile half open) | YOU + LAPTOP |
| 26 | 26 | listeners for the blind listening test | YOU |
| new (25 Nov) | 27 | documentation: the handbook's "(unconfirmed)" items (`V1_HQ_ADAPTIVE` settled 26 Nov: on) | YOU |
| new (26 Nov) | 28 | Get written confirmation of commercial use from AI4Bharat / legal review | YOU |
| new (26 Nov) | 29 | auto mode on `/live`: stock voices, the breakers on a link that hiccups, the meaning check's first step | YOU + LAPTOP |

New in v1.1 WS5, inside the items above: the deploy kit (items 4, 8-11), the backend-only start on the machine
(item 2), the voice A/B kit (item 8), the translation A/B with its rule (item 9), the licence guard on the speaker
model (item 4).

## 27. Documentation: two things only you can settle (YOU) (new, 25 Nov 2026, from the handbook)

Written while building `docs/handbook/`; nothing in the code changes.

1. **`V1_HQ_ADAPTIVE`, on or off. Settled on 26 Nov 2026: on.** (It was: `V1_1_SUMMARY.md` section 3 says on;
   `RUNBOOK.md` section 3, `SUMMARY.md` and `backend/.env.example` say off.) The four now say on with the same
   measured reason, the handbook too, and the code's default is on
   (`docs/handbook/OPEN_QUESTIONS.md` question 20, closed). Rollback: `V1_HQ_ADAPTIVE=false` in `backend\.env`.
2. **Items marked "(unconfirmed)" in the handbook.** Each is a date, a reason or a detail no source or commit
   confirms (for example why v1 runs on the laptop and not the VM, why an end-to-end speech model was never tried,
   which flags were on in the four v1 sessions of 24 Nov). `grep -rn "unconfirmed" docs/handbook` lists them;
   a line from you turns each into a fact.

## 28. Get written confirmation of commercial use from AI4Bharat / legal review (YOU) (new, 26 Nov 2026)

- **What:** IndicF5 (`ai4bharat/IndicF5`) is the copied voice of the product today (9001-9003) and of the planned
  batching server (item 10). Its licence status is **legal confirmation needed**: two sources say two things.
  - Its own Hugging Face card says **MIT** (`license: mit`; https://huggingface.co/ai4bharat/IndicF5, read
    26 Nov 2026). The card says nothing about commercial use; its terms of use are about consent only. Its code
    repository (https://github.com/AI4Bharat/IndicF5) has no licence file.
  - A model fine-tuned from it, `dheeyantra/dhee-indic-f5` (https://huggingface.co/dheeyantra/dhee-indic-f5,
    CC-BY-NC-4.0, read 26 Nov 2026), says: "This model inherits non-commercial terms from its lineage: it is
    fine-tuned from `ai4bharat/IndicF5`, which builds on **F5-TTS** (trained on the **Emilia** dataset,
    CC-BY-NC-4.0) and **IIT-Madras Indic TTS** data (non-commercial). The non-commercial restriction therefore
    carries through to this model."
  - F5-TTS's authors say of their own model: "The pre-trained models are licensed under the CC-BY-NC license due
    to the training data Emilia" (https://github.com/SWivid/F5-TTS, read 26 Nov 2026).
  Everything read, with what could not be fetched: `MODELS.md`, "checked on 26 Nov 2026".
- **Why deferred:** it is not a thing code or a measurement can settle. Whether IndicF5's weights began from
  F5-TTS's pre-trained weights is not stated on any AI4Bharat page, and whether an MIT tag by the model's authors
  is enough for a paid product is a lawyer's question. The claim comes from a third party, which also sells a
  commercial licence for its own model.
- **What to do (no command):**
  1. Write to AI4Bharat (the contact on https://ai4bharat.iitm.ac.in or the model page's discussion tab) and ask,
     in writing: (a) may IndicF5's released weights be used in a commercial, paid dubbing product; (b) were the
     weights initialised from F5-TTS's pre-trained (Emilia) weights; (c) what terms do the IndicTTS (IIT-Madras),
     LIMMITS, Rasa and IndicVoices-R data put on a model trained on them. Keep the answer.
  2. Or have a lawyer read `MODELS.md` ("checked on 26 Nov 2026") and the three pages above.
  3. The same read should cover Demucs: its code is MIT, and the maintained repository says "The license of the
     weights is not clear" (`MODELS.md`, same section).
- **GPU memory:** none.
- **Verify:** a written answer on file. Then `docs/handbook/MODELS.md` (the IndicF5 row), `MODELS.md` and
  `docs/handbook/OPEN_QUESTIONS.md` question 21 are changed from "legal confirmation needed" to what the answer says.
- **Rollback / if the answer is no:** the copied voice needs another model. Candidates already in the plan:
  Maya 2 (item 8, Apache-2.0, not loaded, no speed control), the hosted copy (`vachana-vc-v1`, vendor terms;
  measured too slow for dense Live speech: 5 of 21 phrases in the copied voice), Indic-Mio (Apache-2.0 by v0's
  engine header, built as a switch; its lines are longer on a voice learned from a fast stream). None is a drop-in.
- **Until then:** do not say IndicF5, or "all our models", is cleared for commercial use
  (`docs/handbook/PITCH_FACTS.md`, "Do not claim").

## 29. Auto mode on `/live`: three decisions from the v1.2 measurement (YOU + LAPTOP) (new, 26 Nov 2026)

- **What:** auto mode was measured against v1.1's best setting on the dense reel
  (`docs/handbook/experiments/EXP-031-auto-mode-dense-reel.md`; 5 runs a setting, taken in turn, Punjabi + Tamil,
  hold fixed at 6 s). As it ships, auto is worse: 66.3% (57.4-75.1) of lines within 0.25 s and 82.4% (71.0-89.3)
  within 1 s, against 79.1% (73.2-81.8) and 90.0% (87.4-94.0) for manual mode with `V1_LIVE_BUDGET=true`; 34
  skipped lines per 10 minutes against 3. Three causes were told apart, and each is a choice only you can make.
  Nothing below was changed by the build: the defaults are your list.
- **Why deferred:** the first is your own decision of 26 Nov (stock voices always on); the second trades
  protection in a real stall for steadiness on a link that only hiccups; the third trades timing for meaning.

**1. Stock voices on `/live` (the largest cause).** A `/live` session without a streamer profile speaks in hosted
stock voices in auto mode and never learns the voice on the stream. The hosted account takes one request at a
time, so two languages queue: 0% copied voice, and from 38 skipped lines in a run to 1, by how fast the hosted
voice is in that hour. A streamer's own session (`/streamer`, recorded voice) is not affected.
  - To get the voice learned from the stream back (with its consent tick), in
    `backend\config\overrides.yaml` remove the `# ` in front of this line and restart the backend:
    ```
    live_stock_default: off
    ```
    The website reads the setting from the backend: the choice "the voice on this stream" and its consent tick
    show again by themselves.
  - Measured with that line: 69.6% (55.7-80.8) within 0.25 s, 83.9% (72.1-90.9) within 1 s, copied voice 83.1%
    (50.9-97.3). Still under "budget on", because of point 2.
  - Rollback: put the `# ` back, restart.

**2. The breakers and the ladder on a link that hiccups.** One health answer slower than 2 s, or one line slower
than 4 s, opens a voice engine's circuit for about 34 s; when all three are open the session speaks in the stock
voice until they close. That happened 13 times in 3 of 5 runs, while the engine's own time was never over 0.62 s:
it was the link. Without breakers the same hiccups cost 3-4 late lines in 900.
  - Option A, keep them (the default): safe in a real stall (EXP-023: every phrase dubbed through a 50 s stall,
    4 of 22 without), unsteady on this link.
  - Option B, switch both off, two more lines in `backend\config\overrides.yaml`:
    ```
    breaker: off
    live_degrade: off
    ```
    Measured with these and the line of point 1: 74.2% (72.4-76.6) within 0.25 s, 88.5% (86.4-90.1) within 1 s,
    5.4 skips per 10 minutes, copied voice 97.0%: close to "budget on", and **no protection when the link really
    goes** (the 24 Nov stalls of 2 min, 44 min and 3 h).
  - Option C, make them slower to act, in `backend\.env` (settings, read in auto mode too). **Not measured:**
    ```
    V1_LINK_PROBE_TIMEOUT_S=4
    V1_BREAKER_VOICE_TIMEOUT_S=6
    V1_BREAKER_OPEN_S=10
    ```
    A better rule would be "two slow health answers in a row before a voice engine's circuit opens"; that is a
    code change and was not made.
  - The real cure is item 2 (the backend beside the engines: no tunnel between them) and item 17 (the tunnel
    watchdog).

**3. The meaning check's first step.** A language's budget was loosened in 16 of 17 auto sessions, the first time
on exactly 6 judged lines in half of the cases (2 lost lines are then enough), while the judge calls about 1 line in 6 "lost" before any
loosening. A loosened language has more lines longer than their slots (Punjabi 40-45% against 16%, Tamil 29-46%
against 25%); the judge then finds fewer lost lines (5-10% at the second step, on few lines).
  - Keep it (default), or ask for more evidence before the first step, in `backend\.env`. **Not measured:**
    ```
    V1_MEANING_MIN_SAMPLES=12
    ```
  - Or switch the loosening off: `meaning_check: off` in the overrides file (lines are still judged and counted).
  - To settle whether the loosened lines are really better: a Tamil and a Punjabi speaker reading the same 20
    lines (item 21 has the same need for Studio).

- **GPU memory:** none.
- **Verify:** after a restart `curl.exe -s http://127.0.0.1:8110/api/v1/flags` shows the overrides in force
  (`"overrides": {...}`); a `/live` session's `/metrics` shows `"rung": "copied"` once the voice is learned. To measure a choice the way EXP-031 did:
  `powershell -File scripts\v1\ab-server.ps1 -Port 8122 -Name try -Mode auto -Overrides "live_stock_default=off"`
  and the replay command of `RUNBOOK.md` section 3.5 (check that nobody is live first; stop the backend after).
- **Rollback:** comment the lines out again (or remove them from `backend\.env`), restart.
- **Also from the same measurement, no decision needed:** the script guard reports a Hindi word left in Devanagari
  inside a Tamil line (3 to 8 lines a session on this reel) but its second translation put only 3 of 72 right; the
  line is spoken as it is and flagged. A fix (write the word in Tamil letters by rule) is not built.
