# Bharat Dub

One voice, every Indian language. Bharat Dub dubs videos and live streams into nine Indian languages and English,
in the speaker's own voice.

| Mode | What it does |
|---|---|
| **Studio** (`/studio`) | Upload a reel, short or video up to 3 minutes. It comes back dubbed in the languages you pick, in your own copied voice, with the background music kept and subtitles. Every line can be edited and re-voiced. |
| **Streamer** (`/streamer`) | Record your voice once, with consent, and go live. Viewers pick a language and hear you in your own voice from the first sentence, timed to your stream. |
| **Live** (`/live`, `/watch/[id]`) | Dub any stream that is playing, for its viewers, in real time, with captions and translated chat. |

A voice is copied only with recorded consent, every output is labelled "AI-dubbed", and uploads are deleted after 24 hours.

**Status.** A working product in development. It runs end to end on real services, and every number below was
measured. It is not open to the public yet: there are no accounts, no hosting and no pricing. The list of what is
missing is in [SPEC.md](SPEC.md), section 20.

See [SPEC.md](SPEC.md) for the product and build spec, [STREAMER_MODE.md](STREAMER_MODE.md) for Streamer mode and
[FRONTEND.md](FRONTEND.md) for the design system.

## How it works

Speech is turned into text, translated the way a creator talks, and spoken again in the same voice, timed to the
video. Each step sits behind an interface in `backend/app/providers/`, so a provider can be replaced without touching
the pipelines, and each has a fallback.

| Step | What runs today | Fallback |
|---|---|---|
| Speech-to-text | Gnani Prisma (REST for Studio, realtime with partial results for Live) | none yet |
| Translation | Gemini Flash and Flash-Lite through an OpenAI-compatible endpoint | the larger model redoes a reply in the wrong script |
| Copied voice, Live and Streamer | Our own engine: IndicF5 (337 M parameters) on an A100, three processes ([gpu_engine/](gpu_engine/README.md)) | Gnani Vachana for the first language, stock voices for the rest |
| Copied voice, Studio | Gnani Vachana | stock voice |
| Stock voices, English | Gnani Timbre | - |
| Music and voice separation | Demucs, on the GPU machine when it is reachable | Demucs on the CPU |
| Speech detection, cutting, mixing | Silero VAD, ffmpeg | fixed windows |

## Layout

```
backend/         FastAPI app (providers, studio, live, streamer), tests, scripts, eval
web/             Next.js (App Router, TypeScript, Tailwind v4)
gpu_engine/      our voice engine and separation service for a GPU machine
ingest_client/   microphone -> backend WebSocket, for a streamer without the browser console
supabase/        SQL migrations
reel_dubber.py   the first single-file version of Studio (reference only)
```

## Setup

Requirements: Python 3.11+, Node 20+, ffmpeg on PATH. Optional: a Supabase project (without it data stays in local
files) and a GPU machine for the voice engine (without it Live uses the fallbacks above).

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

Measured on the real services. Nothing here is estimated. Word error rate has not been measured (there are no
ground-truth clips yet), and how close a copied voice sounds to the speaker needs listeners, not a script.
`python -m eval.run` in `backend/` rebuilds `eval/results.csv` from stored runs.

### Live and Streamer with our own voice engine (20 Nov 2026)

Source: a dense 24.9 s Hindi reel (one fast speaker, no pauses) played three times in real time, the video and its dub
kept in step on the viewer's page (in the Live run the viewer's video was held 9 s behind).

| Run | Phrases in the speaker's voice | First audio p50 / p95 | Dub behind its moment in the video p50 / p95 |
|---|---|---|---|
| Live, voice learned from the stream, Tamil + Bengali | 33 of 33 and 31 of 31 | 3.1 to 3.2 s / 3.8 to 3.9 s | 0.2 to 0.4 s / 1.8 to 3.5 s |
| Streamer, voice recorded beforehand, Punjabi + Bengali | 34 of 34 and 29 of 31 | 3.2 to 3.3 s | 0 s / 1.7 to 2.8 s |

The engine has been made faster since (21 Nov 2026): one line takes 439 ms on the GPU and 0.79 s from the laptop
(before: 742 ms and 1.33 s), three lines at once 0.97 s. One stream in three languages keeps the A100 19% busy on
average. One Live run on the faster engine (21 Nov, Tamil + Bengali, voice learned from the stream): first audio
p50 2.7 s in both languages, 30 of 32 and 33 of 35 phrases in the speaker's voice, the viewer's video held 6 s, the dub
0.3 to 0.4 s behind its moment at the median (p95 2.4 to 2.6 s). Separating 60 s of audio takes 4.0 to 4.8 s on the
GPU against 40.3 s on the laptop CPU.

### Live with stock voices, no GPU (14 Nov 2026)

Source: a 24.9 s Hindi reel (one fast speaker, no pauses) fed in real time, twice. Stock voices. "Heard" is the time
from the end of a phrase to the moment a viewer starts hearing its dub, after earlier phrases have played.
Full report and how to rerun: [LIVE_TEST_REPORT.md](LIVE_TEST_REPORT.md).

| Viewers on | First audio p50 / p95 | Heard p50 / p95 | Phrases skipped |
|---|---|---|---|
| Tamil (4 languages offered) | 2.7 s / 3.6 s | 3.4 s / 5.8 s | 0 of 26 |
| Tamil, Bengali, English at once | 3.5 to 3.8 s / 4.7 to 5.0 s | 3.9 to 6.0 s / 5.5 to 7.5 s | 0 of 26 |
| Tamil, voice learned from the stream | 2.6 s / 3.5 s | 3.5 s / 6.7 s | 3 of 38 |

The speech provider's account runs one request at a time; that is what separates the first row from the second.
Not measured: a live microphone, a phone on a mobile network, sessions longer than 82 s.

### Streamer mode, first measurements (15 Nov 2026)

A streamer records their voice once with consent and goes live from `/streamer`; viewers hear them in their own
voice from the first sentence. Spec: [STREAMER_MODE.md](STREAMER_MODE.md). The copied voice comes from our own GPU
engine (IndicF5, see [gpu_engine/README.md](gpu_engine/README.md)); without it the first language uses the
provider's copied voice and the rest stock voices.

| What | Measured |
|---|---|
| Recording to a ready, tested voice | 17.6 s (score 1.0: the test sentence was heard back word for word) |
| Phrases in the streamer's voice, Tamil and Bengali at once | 33 of 33 in each, from the first phrase |
| Words heard back by Prisma | 87% Tamil, 80% Bengali |
| Dub timed 8 s after speech, viewer page in Edge | 30 of 31 phrases arrived early; 77% started within 1 s of their moment |

Source: the same dense 24.9 s reel fed as a microphone would. Not tested: a person at a real microphone, a real
OBS to YouTube broadcast, a phone.

### Studio (13 Nov 2026)

- A 24.9 s reel into 4 languages with stock voices, nothing cached: 84.9 s in total (Demucs 22.9 s, translation 20.7 s,
  voice 12.2 s, one line shortened and re-voiced 20.8 s).
- Demucs `htdemucs` on CPU: 40.3 s for 60 s of audio (Ryzen 7 7435HS).
- Since 14 Nov the target languages are translated at once: on a 13.8 s reel into 2 new languages the translate stage took
  1.3 s instead of 3.4 s (one run each, different language pairs).

## Credits

Models: IndicF5 (AI4Bharat) and Vocos for the copied voice, Demucs (Meta) for separation, Silero VAD, Gnani AI
(Prisma speech-to-text, Timbre voices, Vachana voice cloning), Gemini for translation.
Software: FastAPI, Next.js, Tailwind CSS, GSAP, Lenis, Lucide icons, httpx, websockets, PyTorch, ffmpeg, Supabase.
Typefaces: Instrument Serif, Geist, Anek, Noto.
AI-dubbed output is labelled "AI-dubbed by Bharat Dub".
