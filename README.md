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

Measured on the real Gnani and Gemini APIs. Nothing here is estimated. `backend/eval/run.py` (WER on 20 clips,
slot-fit %) is not written yet, so those numbers are missing.

### Live (14 Nov 2026)

Source: a 24.9 s Hindi reel (one fast speaker, no pauses) fed in real time, twice. Stock voices. "Heard" is the time
from the end of a phrase to the moment a viewer starts hearing its dub, after earlier phrases have played.
Full report and how to rerun: [LIVE_TEST_REPORT.md](LIVE_TEST_REPORT.md).

| Viewers on | First audio p50 / p95 | Heard p50 / p95 | Phrases skipped |
|---|---|---|---|
| Tamil (4 languages offered) | 2.7 s / 3.6 s | 3.4 s / 5.8 s | 0 of 26 |
| Tamil, Bengali, English at once | 3.5 to 3.8 s / 4.7 to 5.0 s | 3.9 to 6.0 s / 5.5 to 7.5 s | 0 of 26 |
| Tamil, voice learned from the stream | 2.6 s / 3.5 s | 3.5 s / 6.7 s | 3 of 38 |

The Gnani account runs one request at a time; that is what separates the first row from the second.
Not measured: a live microphone, a phone on a mobile network, sessions longer than 82 s.

### Studio (13 Nov 2026)

- A 24.9 s reel into 4 languages with stock voices, nothing cached: 84.9 s in total (Demucs 22.9 s, translation 20.7 s,
  voice 12.2 s, one line shortened and re-voiced 20.8 s).
- Demucs `htdemucs` on CPU: 40.3 s for 60 s of audio (Ryzen 7 7435HS).
- Since 14 Nov the target languages are translated at once: on a 13.8 s reel into 2 new languages the translate stage took
  1.3 s instead of 3.4 s (one run each, different language pairs).

## Credits

FastAPI, Next.js, Tailwind CSS, GSAP, Lenis, Lucide icons, httpx, websockets, Demucs (Meta), Silero VAD, Supabase.
Typefaces: Instrument Serif, Geist, Anek, Noto.
Speech models by Gnani AI. AI-dubbed output is labelled "AI-dubbed by Bharat Dub".
