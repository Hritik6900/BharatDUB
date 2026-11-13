# Bharat Dub

One voice, every Indian language. **Studio** dubs your reels and shorts into Tamil, Bengali, Telugu and English in your own
cloned voice, with the background music kept. **Live** dubs a Hindi/Hinglish stream for viewers in real time.

Built on Gnani AI models: Prisma (speech-to-text), Timbre (text-to-speech) and Vachana voice cloning. Translation uses
an OpenAI-compatible LLM (Evon or a backup).

See [SPEC.md](SPEC.md) for the build spec and [FRONTEND.md](FRONTEND.md) for the design system.

## Layout

```
backend/         FastAPI app (providers, studio, live), tests, scripts/smoke.py
web/             Next.js (App Router, TypeScript, Tailwind v4)
ingest_client/   streamer mic -> backend WebSocket (M3)
supabase/        SQL migrations
reel_dubber.py   single-file Studio prototype (reference)
```

## Setup

Requirements: Python 3.11+, Node 20+, ffmpeg on PATH (needed from M2 on), a Supabase project.

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows; on macOS/Linux: source .venv/bin/activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cp .env.example .env            # fill in GNANI_API_KEY, LLM_*, SUPABASE_*
uvicorn app.main:app --reload   # http://localhost:8000/health
pytest                          # offline tests (fake providers), no credits used
python -m scripts.smoke         # real API calls, prints latencies
python -m scripts.smoke --ref my_voice.wav --consent --vc-langs   # voice-clone language check
python -m scripts.dub_file my_reel.mp4 --langs ta-IN               # full Studio run, prints stage timings
```

Without `SUPABASE_*` the backend uses a local JSON store and serves outputs from `/files/...`, so you can run
everything on a laptop. Demucs downloads its model weights (~80 MB) on first use.

Try a job over HTTP:

```bash
curl -F file=@reel.mp4 -F target_langs=ta-IN,bn-IN -F owns_video=true localhost:8000/api/jobs
curl -N localhost:8000/api/jobs/<job_id>/events     # live progress (SSE)
curl localhost:8000/api/jobs/<job_id>/outputs
```

`GNANI_MAX_CONCURRENCY` defaults to 1 because the Gnani docs show a "1 active request at a time" account limit.
Raise it only if app.gnani.ai shows a higher limit for your account.

### Quick start without keys (mock mode)

```powershell
.\dev.ps1 -Mock     # backend (simulated AI, data in backend\data-mock) + frontend, in two windows
```

Open http://localhost:3000. A banner says the AI is simulated: transcripts come from a few sample
Hinglish lines, translations from a small hand-written phrasebook, and voices are tones, not speech.
Demucs, Silero, ffmpeg, the cache, live chunking and all the UI run for real. Mock results use their own
cache and data folder, so they never mix with real runs. Use `.\dev.ps1` (no flag) once `backend\.env` has keys.

If port 8000 is taken on your machine, run the backend on another port and set
`NEXT_PUBLIC_API_BASE` / `NEXT_PUBLIC_WS_BASE` in `web\.env.local` to match (they are read at build time).

### Database

Run `supabase/migrations/0001_init.sql` in the Supabase SQL editor (or `supabase db push`). It creates the tables,
enables RLS (the backend uses the service key) and creates the private `uploads`, `voices` and `renders` buckets.

### Web

```bash
cd web
npm install
cp .env.example .env.local
npm run dev                     # http://localhost:3000
```

## Results

No numbers yet. This section only ever holds measured results from `backend/eval/run.py` (M6).

## Credits

FastAPI, Next.js, Tailwind CSS, GSAP, Lenis, Lucide icons, httpx, websockets, Demucs (Meta), Silero VAD, Supabase.
Typefaces: Instrument Serif, Geist, Anek, Noto.
Speech models by Gnani AI. AI-dubbed output is labelled "AI-dubbed by Bharat Dub".
