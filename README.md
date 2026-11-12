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
pip install -r requirements.txt
cp .env.example .env            # fill in GNANI_API_KEY, LLM_*, SUPABASE_*
uvicorn app.main:app --reload   # http://localhost:8000/health
pytest                          # mocked provider tests, no credits used
python -m scripts.smoke         # real API calls, prints latencies
python -m scripts.smoke --ref my_voice.wav --consent --vc-langs   # voice-clone language check
```

`GNANI_MAX_CONCURRENCY` defaults to 1 because the Gnani docs show a "1 active request at a time" account limit.
Raise it only if app.gnani.ai shows a higher limit for your account.

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

FastAPI, Next.js, Tailwind CSS, httpx, websockets, pydub, Demucs (Meta), Silero VAD, Supabase.
Speech models by Gnani AI. AI-dubbed output is labelled "AI-dubbed by Bharat Dub".
