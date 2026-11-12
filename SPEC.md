# SPEC.md — Bharat Dub

> Build spec. Read this whole file before writing code. When something here conflicts with
> what you find in the official Gnani docs (https://docs.gnani.ai), the docs win: fix the code and update this file.

## 1. What we are building

**Bharat Dub** is one website with two modes that share one backend, one AI-provider layer and one voice profile:

| Mode | Route | What it does | Speed target |
|---|---|---|---|
| **Studio** | `/studio` | Creator uploads their own Reel/Short/YouTube video (≤ 3 min). It comes back dubbed into Tamil / Bengali / Telugu / English etc., in the creator's own cloned voice, background music kept, with subtitles. | 60 s reel → 2–3 min |
| **Live** | `/live` (streamer console) + `/watch/[id]` (viewer) | Streamer streams on YouTube Live in Hindi/Hinglish. Viewers open `/watch/[id]`, pick a language and hear the streamer dubbed live, with captions. Viewers can chat in their language; the streamer sees it translated. | 3–5 s behind the speaker |
| Shared | `/voices`, `/glossary`, `/dashboard` | Voice profile (with consent), glossary of words never translated, usage + latency stats. | — |

Two deadlines use the same site:
- **Gnani "Great Indian AI Internship Challenge"**: must use Gnani models (Prisma STT, Timbre TTS; Evon LLM is a bonus). Target submission: 13 Nov 2026 night.
- **Vihaan X hackathon (IEEE DTU), E-Sports track**: 14–15 Nov 2026, 24 h, live judging.

The demo must be bulletproof and every claim must be backed by a measured number.

## 2. Golden rules

1. **API-first modular monolith.** One FastAPI backend, one Next.js frontend. No microservices, no Kubernetes, no GPU.
2. **Providers behind interfaces.** All STT/LLM/TTS calls go through `backend/app/providers/`. Pipelines never call HTTP APIs directly.
3. **Cache every Studio stage** by `hash(input) + stage settings`. Editing one translated line must re-run only stages 7–10 for that line. Never re-run STT unless audio changed (STT costs credits).
4. **Consent gates cloning.** No call to the voice-clone endpoint unless the voice profile has `consent_at` set. No exceptions, no debug bypass.
5. **Measure everything.** Every Studio stage and every Live chunk records timings into `metrics`. The UI shows real numbers, never fake ones.
6. **Secrets only from env.** Never hardcode keys, never log them, never send them to the browser.
7. **Small, working increments.** Finish a milestone end-to-end (section 13) before starting the next. Commit after each working step with a clear message.
8. **Fail soft in demos.** Every external call has a timeout, one retry, and a visible fallback (see per-stage table).
9. Use straight ASCII quotes in code; keep functions small; type-hint Python; TypeScript strict mode.

## 3. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn, httpx (async), websockets, pydantic v2 |
| Audio | ffmpeg (system), pydub, `silero-vad`, `demucs` (htdemucs, CPU OK), numpy, soundfile |
| DB + files | Supabase (Postgres + Storage), `supabase` Python client |
| Frontend | Next.js (App Router) + TypeScript + Tailwind CSS |
| Live audio in browser | Web Audio API (AudioContext, scheduled buffers), WebSocket |
| YouTube | YouTube IFrame Player API on `/watch/[id]` |
| Streamer client | Python: `sounddevice` mic capture → WebSocket |
| Demo exposure | cloudflared or ngrok tunnel |

Do **not** self-host Evon. Use a hosted OpenAI-compatible endpoint.

## 4. Environment variables (`backend/.env`, `web/.env.local`)

```
# backend
GNANI_API_KEY=
GNANI_BASE=https://api.vachana.ai
GNANI_MAX_CONCURRENCY=1  # account limit: "Only 1 active request is allowed at a time" (429 otherwise)
LLM_BASE_URL=            # OpenAI-compatible, ends with /v1 (Evon endpoint, or backup)
LLM_API_KEY=
LLM_MODEL=               # e.g. gnani/gnani-evon-v3.3-30B-A3B
LLM_MODEL_FAST=          # optional low-latency model for Live; defaults to LLM_MODEL
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
UPLOAD_TTL_HOURS=24
MAX_VIDEO_SECONDS=180
# web
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000
```

Ship `backend/.env.example` and `web/.env.example` with these keys and no values.

## 5. Repository layout

```
bharat-dub/
  SPEC.md
  FRONTEND.md               # design system, motion, components (owns everything visual in web/)
  README.md                 # setup, architecture, attribution, measured results
  reel_dubber.py            # single-file Studio prototype (reference only)
  supabase/migrations/      # SQL for section 10
  backend/
    app/
      main.py               # FastAPI app, routers, CORS
      config.py             # pydantic Settings from env
      db.py                 # Supabase client + small repo functions
      providers/
        base.py             # Protocols: STT, StreamingSTT, LLM, TTS
        http.py             # shared retry/timeout/429-backoff + Gnani concurrency gate
        stt_gnani.py
        tts_gnani.py
        llm_openai.py
      studio/
        runner.py           # job state machine, stage order, cache
        stages/
          extract.py separate.py segment.py transcribe.py translate.py
          voice.py fit.py mix.py render.py
        routes.py
      live/
        session.py          # create/stop sessions, state
        pipeline.py         # ingest -> STT -> assembler -> fan-out -> TTS -> bus
        assembler.py
        bus.py              # per-session, per-language pub/sub
        chat.py
        routes.py           # REST + WebSockets
      shared/
        voices.py glossary.py metrics.py audio_utils.py
    scripts/smoke.py        # hits each provider once, prints latency
    eval/
      clips/ gaming/ run.py results.csv
    tests/
    requirements.txt
    .env.example
  ingest_client/
    client.py               # mic -> 16 kHz mono PCM16 -> /ws/ingest/{session}
    requirements.txt
  web/
    app/
      page.tsx              # landing: two big cards, Studio | Live
      studio/page.tsx       # upload + language picker + voice choice
      studio/[jobId]/page.tsx  # progress, review editor, downloads, A/B player
      live/page.tsx         # streamer console
      watch/[id]/page.tsx   # viewer
      overlay/[id]/page.tsx # OBS browser source (translated chat)
      voices/page.tsx glossary/page.tsx dashboard/page.tsx
    components/ lib/
    .env.example
```

`reel_dubber.py` (already written, single-file prototype) is the reference implementation for Studio. Port its logic into `studio/stages/` instead of rewriting from scratch.

## 6. Gnani API reference (verified against docs.gnani.ai on 2026-11-13)

Auth header on every call: `X-API-Key-ID: <GNANI_API_KEY>`. Base: `https://api.vachana.ai`.

**Account concurrency:** the docs show `429 RATE_LIMITED: "Only 1 active request is allowed at a time"` on STT, TTS,
SSE and VC, with no `Retry-After`. All Gnani REST calls go through one process-wide semaphore
(`GNANI_MAX_CONCURRENCY`, default 1) and back off on 429. Per-account limits live at app.gnani.ai; raise the setting
only after checking there. Other errors: 401 bad key, 402 out of credits, 403 `SCOPE_NOT_ALLOWED`.

### 6.1 STT REST (Studio)
- `POST /stt/v3`, multipart: `audio_file`, `model=prisma-v3.0` (omit = prisma-v2.5), `language_code=indic-auto` (or `hi-IN`, or up to 4 comma-separated codes like `hi-IN,en-IN`; v3 only), optional `format` = `verbatim` (default) | `transcribe` (ITN) | `codemix` | `transliterate`.
- Useful v3 extras: `keyterms` (≤ 200, feed the glossary), `previous_text` (last 600 chars, context).
- Audio: WAV/MP3/OGG/FLAC/AAC/M4A (detected from file extension), **max 30 s**, min 0.1 s → we send segments ≤ 25 s.
- Response: `{success, request_id, transcript, model, detected_language_code, processing_time, end_to_end_latency}`; `truncated: true` if cut. Empty speech → `transcript: ""`.
- Error: `{success:false, error:{type, message}}` (e.g. `MAX_AUDIO_DURATION_EXCEEDED`, `EMPTY_AUDIO`).

### 6.2 STT Realtime (Live)
- `wss://api.vachana.ai/stt/v3/stream`
- Upgrade headers: `x-api-key-id`, `model: prisma-v3.0` (**default is v2.5**; unknown values silently ignored), `language_code: indic-auto` (required), `x-sample-rate: 16000`. Optional VAD headers: `x-min-silence-ms` (500), `x-vad-threshold` (0.7), `x-idle-timeout-sec` (60).
- Send binary PCM16 LE mono, 16 kHz, **exactly 1024-byte frames at real-time cadence (one per 32 ms), never burst**. Send `{"type":"commit"}` to close the current utterance. End of stream: commit, ~1 s of silence, then close.
- Receive JSON (all have `type`, `timestamp`): `connected`, `speech_start`, `processing` (speech ended, transcribing), `transcript` `{text, segment_id, segment_index, utterance_id, latency, audio_duration_ms, is_final, detected_language_code}`, `error` `{message}`.
- **No partial/interim transcripts.** Every `transcript` event is final (`is_final: true`), one per utterance. The assembler treats each as final text; `processing` is the earliest end-of-speech signal (use it as `t_speech_end`).
- Session cap 15 min (close 1001) → the pipeline must reconnect transparently. Bad header → close 1008.

### 6.3 TTS
- Body: `{text, voice, model:"timbre-v2.5"|"timbre-v3.0", language, speed (0.85–1.15), audio_config:{sample_rate, num_channels, sample_width, encoding:"linear_pcm", container:"wav"|"raw"|"mp3"|"ogg"}}`.
- `sample_rate` ∈ {8000, 16000, 22050, 24000, 44100, 48000} (default 48000). `language` ∈ hi-IN, en-IN, ta-IN, te-IN, kn-IN, ml-IN, mr-IN, pa-IN, bn-IN, gu-IN, hi-en, auto.
- REST: `POST /api/v1/tts/inference` → raw binary audio (not JSON).
- SSE: `POST /api/v1/tts/sse`, same body → events `start`, `chunk` (`{chunk_index, audio:<base64>, is_final}`), `complete` (`audio:""`, `is_final:true`).
- Realtime WS: `wss://api.vachana.ai/api/v1/tts` (header `X-API-Key-ID`), send one JSON request at a time; receive `{"type":"start"}`, `{"type":"audio","data":{chunk_index, audio:<base64>, is_final}}`, `{"type":"complete"}`, `{"type":"error","message"}`.
- Voices are model-specific (a v2.5 voice with v3.0 → 400). Default map (`VOICE_BY_LANG` in config, timbre-v2.5, voice in its preferred language):
  `hi-IN` Nalini (F) / Deepak (M) · `ta-IN` Asmita (F, all Tamil voices are F) · `bn-IN` Kirra (F) / Dhruva (M) ·
  `te-IN` Suhana (F, all Telugu voices are F) · `en-IN` Kaveri (F) / Pranav (M) · `kn-IN` Saanvi · `ml-IN` Reshma ·
  `mr-IN` Zahira · `gu-IN` Falak · `pa-IN` Mehuli. Timbre v3.0 has 13 voices that each speak all 10 languages
  (e.g. Shivani F, Avinash M) — an option if we want one consistent voice across languages.

### 6.4 Voice cloning
- Embedding: `POST /api/v1/tts/voice-clone/embeddings`, multipart `audio_file` (5–30 s clean speech) →
  `{success, message, data:{voice_clone_embedding:{embedding:<string>, shape:[1,768], dtype:"torch.bfloat16"}}}`.
  Note the nesting under `data.voice_clone_embedding`.
- Synthesis: same TTS endpoints with `model:"vachana-vc-v1"` and `speaker_embedding:{embedding, shape, dtype}`; **no `voice` and no `language` field**. VC `audio_config`: sample_rate 8000–44100, encoding `linear_pcm`|`oggopus`, container `wav`|`raw`|`mp3`|`ogg`|`mulaw`.
- **Unknown:** the docs do not say which languages VC speaks. First task with a key: run `scripts/smoke.py --vc-langs` (one Tamil, one Bengali, one English line) and listen. If quality is poor, fall back to stock Timbre voices for those languages and keep cloning for Hindi.

## 7. Provider interfaces (`providers/base.py`)

```python
class STT(Protocol):
    async def transcribe(self, wav_path: str, lang: str = "indic-auto") -> STTResult: ...

class StreamingSTT(Protocol):
    async def stream(self, pcm_frames: AsyncIterator[bytes], lang: str) -> AsyncIterator[TranscriptEvent]: ...

class LLM(Protocol):
    async def translate_batch(self, lines: list[str], target: str, glossary: list[str]) -> list[str]: ...
    async def translate_chunk(self, text: str, target: str, glossary: list[str], context: list[str]) -> str: ...
    async def shorten(self, text: str, target: str, max_seconds: float) -> str: ...

class TTS(Protocol):
    async def synth(self, text: str, lang: str, voice: VoiceSpec) -> bytes: ...           # full WAV
    async def synth_stream(self, text: str, lang: str, voice: VoiceSpec) -> AsyncIterator[bytes]: ...  # PCM chunks
```

`VoiceSpec` = either `{"kind":"stock","voice":"<name>"}` or `{"kind":"clone","embedding":{...}}`.

LLM prompt rules (both modes):
- Natural spoken style of the target language, the way a creator talks, not textbook.
- Keep glossary words and brand names in English exactly.
- Keep roughly the same spoken length as the source (Studio) / be brief (Live).
- Studio batch: return ONLY a JSON array of strings, same length and order. Strip anything before the first `[` and after the last `]` (reasoning models may think out loud). On count mismatch, retry once, then fall back to per-line calls.

## 8. Studio pipeline

| # | Stage | Implementation | Output | On failure |
|---|---|---|---|---|
| 1 | Ingest | ffprobe; reject > `MAX_VIDEO_SECONDS` | job row | clear error to user |
| 2 | Extract | ffmpeg → 44.1 kHz mono WAV | `full.wav` | fail job |
| 3 | Separate | `python -m demucs --two-stems=vocals -n htdemucs` | `vocals.wav`, `no_vocals.wav` | continue without background, show warning |
| 4 | Segment | Silero VAD on 16 kHz; merge gaps < 0.35 s; cap 25 s | segments | fixed 20 s windows |
| 5 | Transcribe | Prisma REST per segment (concurrency = `GNANI_MAX_CONCURRENCY`, default 1) | `segments.src_text` | 1 retry, then `hi-IN` |
| 6 | Translate | `translate_batch` per target language | `translations.text` | see LLM rules |
| 7 | Voice | `synth` per line (stock or clone) | line WAVs | clone fails → stock voice |
| 8 | Fit | if longer than slot: ffmpeg `atempo` ≤ 1.35; still too long → `shorten` then re-synth | fitted WAVs | accept 1.35x |
| 9 | Mix | overlay dub on background; duck background −6 dB under speech | `mix_<lang>.wav` | — |
| 10 | Render | ffmpeg mux (copy video, AAC audio) + SRT | `<name>_<lang>.mp4`, `.srt` | fail job with logs |

- Slot for line *i* = from its start to the start of line *i+1* (last line: to end of video).
- Job status updates stream to the UI via Server-Sent Events: `GET /api/jobs/{id}/events`.
- Review editor: editing a line sets `edited=true`, re-runs 7–10 for that line only, then re-mixes.

## 9. Live pipeline

```
ingest_client (mic, 16 kHz PCM16) --WS--> /ws/ingest/{sid}
  -> StreamingSTT (Prisma realtime)
  -> Assembler: close a chunk on sentence punctuation, OR 1.2 s silence, OR 6 s max
  -> fan-out: for each target lang in parallel:
        translate_chunk (context = last 3 source chunks, glossary)
        -> publish caption immediately
        -> synth_stream -> publish audio frames
  -> Bus (per session, per language) --WS--> /ws/watch/{sid}?lang=ta-IN
```

Rules:
- Each chunk gets `seq` (monotonic per session) and `t_speech_ms` (when the source speech started, session clock).
- Per-language worker processes chunks **in order**; a slow chunk must not reorder audio.
- Captions are published as soon as translation is ready (before audio) so the UI feels instant.
- Record per chunk: `t_speech_end`, `t_stt_final`, `t_translated`, `t_first_audio`, per language. `/api/live/sessions/{id}/metrics` returns p50/p95 of `t_first_audio - t_speech_end`.
- Streamer must wear headphones. `ingest_client` applies a simple noise gate (RMS threshold, configurable).
- **Concurrency caveat:** with a 1-active-request account limit, 3 languages of TTS in parallel will 429. Before M5, confirm the real limit at app.gnani.ai; if it is 1, serialize TTS per chunk across languages (and measure the latency cost).

Watch-channel messages (JSON text frames):
```json
{"type":"caption","seq":42,"lang":"ta-IN","text":"...","t_speech_ms":183200}
{"type":"audio","seq":42,"lang":"ta-IN","sample_rate":44100,"pcm_b64":"...","last":false}
{"type":"stats","p50_ms":3400,"p95_ms":5100}
```

Viewer player (`/watch/[id]`):
- YouTube IFrame embed (muted by default, original audio toggle).
- Language switcher (Hindi original / Tamil / Bengali / English).
- Web Audio scheduler: decode PCM16 → Float32 → AudioBuffer, schedule back-to-back with a 300 ms jitter buffer.
- **Sync offset**: default from session config, plus a slider (−5 s … +10 s) saved per session.
- Live captions under the video; latency badge ("Dub delay 3.6 s") from `stats` messages.
- Chat box: viewer types in any language → `/ws/chat/{sid}` → translated into the streamer's language → shown on `/overlay/[id]` (OBS browser source) and the `/live` console.

## 10. Data model (Supabase SQL)

Lives in `supabase/migrations/0001_init.sql` (tables + storage buckets `uploads`, `voices`, `renders`).
Storage buckets: `uploads` (deleted after `UPLOAD_TTL_HOURS`), `voices`, `renders`. Live audio is never stored.

## 11. API contract

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jobs` | multipart video + `target_langs` + `voice_profile_id?` → `{job_id}` |
| GET | `/api/jobs/{id}` | job + stage timings |
| GET | `/api/jobs/{id}/events` | SSE progress |
| GET | `/api/jobs/{id}/segments?lang=` | lines with source, translation, timing |
| PATCH | `/api/jobs/{id}/translations/{tid}` | edit one line → partial re-render |
| POST | `/api/jobs/{id}/render` | render selected langs |
| GET | `/api/jobs/{id}/outputs` | signed URLs for MP4 + SRT |
| POST | `/api/voices` | sample + `consent_text` + `consent=true` → embedding |
| DELETE | `/api/voices/{id}` | delete sample + embedding |
| GET/POST/DELETE | `/api/glossary` | glossary CRUD |
| POST | `/api/live/sessions` | `{youtube_video_id, target_langs, voice_profile_id?}` → `{session_id}` |
| POST | `/api/live/sessions/{id}/start` · `/stop` | lifecycle |
| GET | `/api/live/sessions/{id}/metrics` | p50/p95, chunk count |
| WS | `/ws/ingest/{sid}` | PCM up from streamer |
| WS | `/ws/watch/{sid}?lang=` | captions + audio + stats down |
| WS | `/ws/chat/{sid}` | viewer chat up, translated chat down |
| GET | `/api/dashboard` | totals: minutes dubbed, jobs, sessions, latency |

## 12. Frontend: pages and the "wow" details

See FRONTEND.md for the design system. Page list:
- **Landing `/`**: two big cards (Studio, Live), one-line pitch, a looping 10 s before/after clip.
- **`/studio`**: drag-and-drop upload, language chips (multi-select), voice choice (my cloned voice / stock), "I own this video" checkbox (required).
- **`/studio/[jobId]`**: stage-by-stage progress with live timings; when done, an **A/B player** (original vs dubbed, same timeline, one click to switch language); review editor table (source | translation | play | edit); download buttons.
- **`/voices`**: record 20–30 s in-browser or upload; consent text the speaker must read aloud; delete button.
- **`/live`**: create session (YouTube video id, languages), start/stop, live transcript, per-language captions, latency graph (last 60 chunks), translated chat feed, copy-link to `/watch/[id]`.
- **`/watch/[id]`**: see section 9. Mobile-first. Big language buttons.
- **Demo mode** (`/watch/[id]?demo=1`): shows all languages' captions side by side and the latency badge large, for the stage.
- **`/dashboard`**: minutes dubbed, languages used, median Studio turnaround, Live p50/p95.
- Every AI output carries a small "AI-dubbed" label.

## 13. Milestones and acceptance criteria

| # | Milestone | Done when |
|---|---|---|
| M0 | Scaffold | Monorepo, FastAPI `/health`, Next.js landing, Supabase tables + buckets, `.env.example` files, README setup |
| M1 | Providers | Unit-tested `stt_gnani`, `tts_gnani` (stock + clone), `llm_openai`; script `scripts/smoke.py` hits each once and prints latency. VC language check done (section 6.4) |
| M2 | Studio core | `POST /api/jobs` on a 60 s Hinglish reel produces a playable Tamil MP4 + SRT; stage timings saved; cache prevents repeat STT |
| M3 | Live core | `ingest_client` → `/watch` plays Tamil audio + captions for live mic speech; p50 latency measured and shown |
| M4 | Site | All pages in section 12 working against real backend; review editor partial re-render works |
| M5 | Live polish | 3 languages in parallel, reverse chat + OBS overlay, sync slider, clone voice live (if 6.4 passed) |
| M6 | Eval + demo | `eval/run.py` produces `results.csv` (WER on 20 clips, slot-fit %, Studio turnaround, Live p50/p95); README "Results" section filled with measured numbers only; demo script rehearsed |

Order if working alone: M0 → M1 → M2 → M3 → M4 → M5 → M6. With a team: Studio (M2) and Live (M3) in parallel after M1.

## 14. Testing and evaluation

- `pytest` for providers (mock HTTP), assembler rules, fit/slot math, SRT formatting, cache keys.
- `eval/run.py`: reads `eval/clips/*.wav` + `*.txt` ground truth → WER; runs Studio on `eval/reels/` → turnaround + slot-fit %; replays `eval/gaming/*.wav` through the Live pipeline at real-time speed → latency p50/p95.
- Never put an unmeasured number in the UI, README, post or pitch.

## 15. Safety, consent, legal

- Cloning requires a voice profile with `consent_at`; the backend refuses otherwise (HTTP 403).
- Upload form requires "I own this video or have permission".
- Outputs labelled "AI-dubbed by Bharat Dub" (SRT first cue + UI label).
- Uploads auto-deleted after 24 h; voice profiles deletable in one click.
- No dubbing of third-party broadcasts (sports, news) in this version.
- README credits open-source tools used (Demucs, Silero VAD, FastAPI, Next.js, etc.).

## 16. Known unknowns (verify early, record answers here)

- [ ] Does `vachana-vc-v1` speak Tamil/Bengali/English well? **Answered in part (docs, 2026-11-13):** there is no `language` field (and no `voice` field) for VC, and the docs do not list the languages VC supports. Still needs a listening test with a key (`scripts/smoke.py --vc-langs`).
- [x] Timbre voice names per language → section 6.3 (`VOICE_BY_LANG`). Tamil and Telugu have female voices only on v2.5.
- [x] Prisma realtime partial vs final → **no partials**; each `transcript` event is final (`is_final: true`); `processing` marks end of speech.
- [x] Supported TTS `sample_rate` → 8000, 16000, 22050, 24000, 44100, 48000 (VC: 8000–44100). We use 44100.
- [ ] Hosted Evon endpoint available? If not, which backup LLM. (Needs `LLM_BASE_URL`; not configured yet.)
- [ ] Vihaan X rules on code written before the event.
- [ ] **New:** real concurrency limit for our Gnani account (docs show 1 active request; check app.gnani.ai). It decides whether Live can do 3 languages in parallel.
- [ ] **New:** measured smoke latencies (needs `GNANI_API_KEY`).

## 17. First prompt

> Read SPEC.md fully. Then do M0 and M1 only. Start by creating the monorepo layout, `.env.example` files and the
> Supabase SQL migration. Implement the three providers behind the protocols in section 7, with retries and timeouts,
> and `scripts/smoke.py`. Run the smoke script, show me the latencies, then answer the "Known unknowns" you can verify
> and update section 16. Stop and wait for me before starting M2.
