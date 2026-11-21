# SPEC.md — Bharat Dub

> Product and build spec. Read this whole file before writing code. When something here conflicts with a
> provider's official docs (Gnani: https://docs.gnani.ai), the docs win: fix the code and update this file.

## 1. What we are building

**Bharat Dub** is a product: one website with three modes that share one backend, one AI-provider layer and one voice profile:

| Mode | Route | What it does | Speed target |
|---|---|---|---|
| **Studio** | `/studio` | Creator uploads their own Reel/Short/YouTube video (≤ 3 min). It comes back dubbed into Tamil / Bengali / Telugu / English etc., in the creator's own cloned voice, background music kept, with subtitles. | 60 s reel → 2–3 min |
| **Live** | `/live` (streamer console) + `/watch/[id]` (viewer) | Streamer streams on YouTube Live in Hindi/Hinglish. Viewers open `/watch/[id]`, pick a language and hear the streamer dubbed live, with captions. Viewers can chat in their language; the streamer sees it translated. | 3–5 s behind the speaker |
| **Streamer** | `/streamer` | A streamer records their voice once (consent sentence read aloud) and goes live. Viewers hear them in their own voice from the first sentence, timed to the stream. Spec: STREAMER_MODE.md. | same as Live |
| Shared | `/voices`, `/glossary`, `/dashboard` | Voice profile (with consent), glossary of words never translated, usage + latency stats. | — |

**Direction (since 21 Nov 2026): a startup product.** Bharat Dub began as an entry for two events, the Gnani AI
challenge (submitted 13 Nov 2026) and the Vihaan X hackathon (14-15 Nov 2026). Both are over and no longer shape
any decision. What that changes:

- **No single-vendor rule.** Each capability (speech-to-text, translation, voice) uses the provider that measures best,
  behind the interfaces in section 7, with a fallback. Today: Gnani Prisma (speech-to-text), Gemini (translation), our
  own IndicF5 engine on a GPU (copied voice in Indian languages), Gnani Timbre (stock voices, English, fallback) and
  Gnani Vachana (copied voice in Studio, fallback in Live). Any of them can be replaced when another measures better.
- **The bar is a stranger using it without us in the room**, not a rehearsed demo: reliability, cost per minute and
  what happens when a provider is down matter as much as the best-case number.
- **Every claim is still backed by a measured number.** Sections 16-19 are the measured history; older entries there
  speak of the events and stay as written.

What a product needs and this code does not have yet is listed in section 20.

## 2. Golden rules

1. **API-first modular monolith.** One FastAPI backend, one Next.js frontend. No microservices, no Kubernetes. The one
   separate service is the GPU engine (`gpu_engine/`: copied voice and separation), optional and reached only through
   `providers/`; with it off everything still runs.
2. **Providers behind interfaces.** All STT/LLM/TTS calls go through `backend/app/providers/`. Pipelines never call HTTP APIs directly.
3. **Cache every Studio stage** by `hash(input) + stage settings`. Editing one translated line must re-run only stages 7–10 for that line. Never re-run STT unless audio changed (STT costs credits).
4. **Consent gates cloning.** No call to the voice-clone endpoint unless the voice profile has `consent_at` set. No exceptions, no debug bypass.
5. **Measure everything.** Every Studio stage and every Live chunk records timings into `metrics`. The UI shows real numbers, never fake ones.
6. **Secrets only from env.** Never hardcode keys, never log them, never send them to the browser.
7. **Small, working increments.** Finish a milestone end-to-end (section 13) before starting the next. Commit after each working step with a clear message.
8. **Fail soft.** Every external call has a timeout, one retry, and a visible fallback (see per-stage table).
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
| Voice engine (optional) | IndicF5 (337 M parameters) + Vocos on an A100, `gpu_engine/`; Demucs on the same machine |
| Exposure until hosted | cloudflared or ngrok tunnel |

Translation runs on a hosted OpenAI-compatible endpoint (Gemini today); we do not host a language model ourselves.

## 4. Environment variables (`backend/.env`, `web/.env.local`)

```
# backend
GNANI_API_KEY=
GNANI_BASE=https://api.vachana.ai
GNANI_MAX_CONCURRENCY=1  # account limit: "Only 1 active request is allowed at a time" (429 otherwise)
LLM_BASE_URL=            # OpenAI-compatible (today Gemini: https://generativelanguage.googleapis.com/v1beta/openai)
LLM_API_KEY=
LLM_MODEL=               # e.g. gemini-3.5-flash
LLM_MODEL_FAST=          # optional low-latency model for Live; defaults to LLM_MODEL
LLM_REASONING_EFFORT=    # optional; `none` for Gemini Flash (hidden thinking otherwise truncates short replies)
LLM_REASONING_EFFORT_FAST=  # optional; for LLM_MODEL_FAST when it needs another value (`minimal` for flash-lite)
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
- **Big-screen view** (`/watch/[id]?demo=1`): shows all languages' captions side by side and the latency badge large, for a wall or a second screen.
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
| M6 | Eval | `eval/run.py` produces `results.csv` (WER on 20 clips, slot-fit %, Studio turnaround, Live p50/p95); README "Results" section filled with measured numbers only |

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
- [x] Hosted Evon endpoint available? Not on the dashboard; backup LLM is Gemini Flash (see below).
- [ ] **New:** real concurrency limit for our Gnani account (docs show 1 active request; check app.gnani.ai). It decides whether Live can do 3 languages in parallel.
- [x] Measured smoke latencies (2026-11-13, real Gnani key, one run each, ~5 s Hindi clip): TTS REST 1.2 s; TTS SSE first chunk
  0.18-0.24 s; STT REST 0.59 s; STT realtime final arrives ~0.76 s after the audio ends (server `latency` field ~170 ms).
- [x] Realtime STT in practice: **no `processing` event is sent** (only `connected`, `speech_start`, `transcript`). The pipeline
  falls back to `t_speech_end = final arrival - 500 ms`. The `connected` config shows `partials_enabled: false`,
  `partial_interval_ms: 450`: partials may exist behind an undocumented switch; not explored.
- [x] LLM: no hosted Evon endpoint on the Gnani dashboard (it lists STT and TTS only), so translation runs on Gemini through its
  OpenAI-compatible endpoint (`LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `gemini-3.5-flash`,
  `LLM_REASONING_EFFORT=none`). Measured 2026-11-13: 1.4-2.2 s for a 3-line batch, ~1.5 s for a live chunk. With thinking on
  it took 4-5 s and truncated the reply; `gemini-3.5-flash-lite` returned the Hinglish untranslated. Prompts now demand
  native script (models answered Hinglish input in romanised Tamil otherwise).
- [x] VC on the real API (2026-11-13): embedding from a 9.8 s sample in 1.4 s; cloned lines in Tamil, Hindi and English were
  transcribed back by Prisma with the same words (intelligibility check, one line each, synthetic source voice). How close it
  sounds to a real person's voice still needs a human listening test.
- Studio can copy the voice **from the uploaded video itself** (`voice_from_video=true` + `voice_consent=true` on `POST /api/jobs`,
  403 without consent). The consent sentence is a checkbox at upload, not read aloud. The runner builds a 5-28 s sample from the
  separated vocals, creates a normal voice profile with `consent_at` ("Voice from <file>") and attaches it to the job; under 5 s
  of speech or a clone error falls back to stock with a warning. The profile is reusable for Live and deletable on `/voices`.
- [x] All ten languages are selectable (2026-11-13): Studio offers all ten (Hindi included, for non-Hindi videos), Live the nine
  non-Hindi ones. Kannada, Malayalam, Marathi, Gujarati and Punjabi were checked once each on the real API: Gemini translation in
  native script, Timbre stock voice (1.2-3.7 s), and Prisma heard the line back with at most one word different.
- [x] **Account concurrency is 1** (2026-11-13: three TTS calls at once, two got 429 "Only 1 active request is allowed at a time").
- [x] Live end to end on the real APIs (2026-11-13, full numbers in LIVE_TEST_REPORT.md; source = a dense 24.9 s Hindi reel
  replayed at real-time speed): stock voices, 3 languages: first audio p50 3.6 s / p95 4.7 s; cloned voice, 1 language: 4.6 s / 5.4 s.
  Clone TTS is not streamed and takes 1.9-3.5 s per line (stock: ~0.5 s to first chunk), so with concurrency 1 only the first
  `live_clone_langs` languages (default = `GNANI_MAX_CONCURRENCY`) use the cloned voice in Live; a chunk already more than
  `live_clone_max_lag_ms` (5 s) late falls back to stock. Stock voices run at `speed` 1.15 in Live (VC ignores `speed`).
- Live can learn the voice **from the stream** (`voice_from_stream=true` + `voice_consent=true` on `POST /api/live/sessions`, 403
  without consent): 12 s of speech frames are collected, cloned, saved as a normal profile ("Voice from live <time>") and used from
  then on; stock voices until then. Measured: ready 33-37 s after the stream starts.
- Live fan-out: every chunk is translated immediately for all languages (captions in order per language); only TTS is queued.
  The viewer plays 1.1x when more than 2 s of audio is waiting and skips a chunk more than 10 s late.
- [x] **Realtime STT partials exist** (found 2026-11-13, not in the docs): upgrade header `x-partials: true` (and
  `x-partial-interval-ms`, we send 300) turns on `partial_transcript` events `{text, stable_text, volatile_text, utterance_id, seq}`
  about every 0.5 s, `speech_end` `{t_ms, audio_ms}` (stream clock, = end of speech + min silence) and `final_transcript`
  (instead of `transcript`). The next utterance's `speech_start` can arrive before the previous `final_transcript`.
  Live cuts phrases from `stable_text` (`Phraser` in `live/assembler.py`: 6-12 words, at a clause boundary) so translation and
  voice start before the speaker pauses; the final only supplies the tail. `LIVE_PARTIALS=false` restores whole-utterance chunks.
- [x] Live latency after phrase chunking (2026-11-13, same 24.9 s reel in real time, 4 languages, one viewer language):
  stock voice, end of phrase to first audio p50 2.3 s / p95 3.6 s, first word of phrase to first audio p50 3.4 s / p95 5.2 s;
  voice learned from the stream p50 4.1 s / p95 4.8 s (first word 5.0 s / 6.6 s). `t_speech_end` now comes from `speech_end`
  for utterance tails and from the partial that first showed the phrase's last word minus 600 ms (an estimate) for phrases.
  **Earlier numbers in this file used final arrival - 500 ms, which the real `speech_end` shows was about 0.3-0.6 s too kind.**
- Live audio is made only for languages a viewer is tuned to (`live_tts_only_heard`), and a phrase more than 8 s late is not
  spoken (`live_skip_after_ms`); captions always go out. Source language is pinned per session (`src_lang`, default `hi-IN`):
  `indic-auto` over game sound produced Bengali/Kannada garbage. `hi-IN,en-IN` is not accepted by the realtime socket.
- Live translation uses `LLM_MODEL_FAST=gemini-3.5-flash-lite` with `LLM_REASONING_EFFORT_FAST=minimal` (`none` is a 400 for
  lite): 0.8-0.95 s per phrase against 1.3-1.5 s for `gemini-3.5-flash`. Lite sometimes returns the Hindi unchanged; such a
  reply (Devanagari in a non-Devanagari target) is re-translated by the main model.
- [x] **"First audio" is not what a viewer hears** (2026-11-14). Phrase chunking cut first audio to 2.3 s but the Tamil dub came
  out 28% longer than the speech (64.4 s for 50.3 s), so audio piled up in the player: heard p50 7.8 s. Now the pipeline keeps a
  per-language playhead (`_playhead`: when a viewer's queued dub ends) and: trims Timbre's silence around every phrase
  (`live_trim_silence`), shortens a phrase with ffmpeg `atempo` up to 1.3x when audio is still waiting (`live_fit*`), skips a
  phrase that would be heard more than 8 s late, and speaks up to 3 waiting phrases in one voice call (`live_merge_max`; the worker
  takes the voice turn `_voice_turn` before choosing its batch). `t_heard:<lang>` is stored per chunk; stats and metrics carry
  `heard_p50_ms`/`heard_p95_ms` (additive) and the UI badges show those. `scripts/live_player_sim.py` replays a run through the
  web player's rules; it agreed with the server estimate within 0.1 s on single-viewer runs.
  Measured (same reel): 1 viewer language heard p50 3.4 s / p95 5.8 s; 3 viewer languages 3.9-6.0 s / 5.5-7.5 s; learned voice
  3.5 s / 6.7 s. Full table in LIVE_TEST_REPORT.md.
- Live translation model is `gemini-3.1-flash-lite` (0.82 s a phrase, 0 of 48 replies in a wrong script;
  `gemini-3.5-flash` 1.02 s and 4 of 48, `gemini-3.5-flash-lite` 1.06 s and 4 of 48, `gemini-3.7-flash` 1.84 s;
  `scripts/live_llm_bench.py`). Any reply with letters outside the target script and Latin (`wrong_script`) is redone once
  by the main model. This supersedes the flash-lite note above.
- Studio translates all target languages at once (`studio_translate_ahead`, `_pretranslate` in the runner): each language's
  translate stage awaits its own task, so stage order, events and cache are unchanged.
- `PUBLIC_API_BASE` must match the port the backend runs on (8010 on the dev laptop): local render URLs are built from it,
  and a wrong port leaves the A/B player without video.
- Live console can take its sound from a browser tab (`getDisplayMedia`, tab only; window/screen share is refused because it
  carries the dub back in and loops). The YouTube link is only an embed: the browser cannot read a cross-origin player's audio.
- [x] **Live sync mode** (2026-11-14 afternoon, `live_sync`). The `/live` console embeds the session's YouTube video; with
  "Sound from: the video on this page" it captures its own tab and sends the player's time on the ingest socket
  (`{"type":"media","t":<s>,"playing":bool}`, read over postMessage `infoDelivery`, `web/lib/youtubeClock.ts`). The pipeline then
  tags every caption and audio message with `media_s` (the video time the phrase was spoken at) and broadcasts
  `{"type":"sync","media_s","delay_ms"}`. `/watch` holds its own player `delay_ms` behind the console's (pause to wait, seek when
  far off) and starts each phrase when its player reaches `media_s`; if the viewer's video is not playing the dub plays as it
  arrives. All fields are additive; with mic or another-tab sound nothing changes.
  The delay starts at 6 s (8.5 s with a copied voice) and grows by what the dub needs when audio keeps arriving after its
  moment (`live_sync_adapt`, limit 15 s). Measured on the dense 24.9 s reel, stock voice, Tamil, 3 loops: in a fast spell of the
  APIs delay 8 s, dub behind its video moment p50 0.3 s / p95 1.9 s, 1 of 39 phrases skipped; in a slow spell delay 10 s,
  p50 0.6 s / p95 2.8 s. Viewer page in Edge: 15 of 18 phrases arrived before their moment, video held within 0.2-2.6 s of target.
  Not measured: a live YouTube broadcast (only uploaded videos), a phone, a person at a microphone.
- [x] **Gnani speed varies through the day** (2026-11-14): stock TTS for a 7-word Tamil phrase took 0.9 s in one hour and
  2.5 s (first chunk 1.2-1.5 s) in another; a call costs about 1.3 s plus 0.25 s per second of audio, so short phrases are the
  expensive ones. Gemini went from 0.8 s to 1.2-2.3 s a phrase in the same hours.
- [x] **Copied voice cannot keep up with dense speech** at one Gnani request at a time: in sync mode with the voice learned
  from the stream only 5 of 21 spoken phrases were in the copied voice and the delay grew to 14.5 s. The copied voice is used
  when there is at least `live_sync_clone_spare_ms` before the audio is needed, else stock.
- `live_brief`: while a language's dub is behind (0.5 s), the live prompt asks for a condensed translation (main point, about
  60% of the words). Without sync mode this cut heard p95 from 5.8 s to 4.6 s (p50 3.4 s unchanged) and speed-ups from 21 to 12
  phrases of about 26, one run each. `live_warmup` makes one tiny translation and voice call when a session starts.
- [x] **Live copied voice on our own GPU engine** (2026-11-14 evening; `GPU_VOICE_URL`, `providers/tts_gpu.py`, `gpu_engine/`).
  This is our own engine, not a Gnani model; it was chosen because it measured best (no single-vendor rule, section 1). IndicF5 on an A100
  (three engine processes, ports 9001-9003 behind an SSH tunnel) speaks every Indian target language in the speaker's
  voice; English and any failure go to the Gnani voices. Empty `GPU_VOICE_URL` = Gnani only, as before.
  - The voice sample is the last 7 s before the first pause (at least 3.5 s, mostly speech), taken only on sessions with
    the stream-voice consent; Prisma transcribes that exact cut, because the engine copies pace and words from the sample
    (a text longer than the audio made every phrase twice too fast). Ready about 9 s into the stream.
  - The engine reads only the language's own letters: "green chicken" in Latin letters came out as noise, in Tamil letters
    word for word. So for GPU languages the live prompt writes English words in the target script (captions too).
  - Speed: the engine at 1.3x kept 70% of the words (Prisma hearing 14 Tamil lines back), normal speed squeezed afterwards
    with `atempo` 82% (untouched: 80%). So the engine speaks at 1.0 and the fit stays with `atempo`.
  - Separate processes work in parallel, replicas inside one process do not: three lines at once 1.19 s against 2.26 s.
    One line is 0.91 s on the machine whatever its length; 1.2-1.7 s from the laptop (machine in Seoul, about 0.45 s per
    request through the tunnel; Opus instead of raw PCM saved about 0.5 s a line).
  - Measured, same dense reel, sync mode, voice learned from the stream, 3 loops. Tamil only: 31 of 32 spoken phrases in the
    copied voice (Gnani clone: 5 of 21), delay 7.5 s (Gnani clone: 14.5 s), behind p50 1.3 s / p95 3.2 s, 2 of 37 skipped,
    80% of words heard back. Tamil + Bengali + Telugu at once: 30-31 of 31 in the copied voice each, delay 9 s, behind
    p50 0.4-1.1 s / p95 2.8-3.2 s, 1 of 34 skipped, 85-89% of words heard back (Bengali, Telugu).
  - Not known: how close the voice sounds to the speaker (needs ears), behaviour with game sound under the voice.
- Live, 14 Nov night. `live_length_budget`: the pipeline measures how long the dubbing voice takes per word in each language
  and how fast the speaker talks, and gives the translator a word limit per phrase (1.15x the speaker's time in step, 0.9x
  when behind, 0.6x when more than 2 s behind). On the dense reel the translator never went over the limit (24 and more
  phrases a run) and phrases needing the 1.3x speed-up fell from 28-29 to 18-20 of about 30. The tail of a line now starts
  when its words were spoken (word count x the speaker's pace), not when the line ended. `/watch` keeps the stream's own
  sound at 18% under the dub (checkbox, on by default).
  The voice sample is joined from short lines (`speech_cut`): pauses over 0.45 s are shortened, speech is left as it was.
  A first version cut every pause to 0.16 s and the copied voice rushed (8 words in 1.4 s, 47% of words heard back); with
  natural pauses 77%. The engine copies the sample's pace, so a rushed sample means a rushed dub.
  With the natural-pace voice the dense reel is still about 1 s behind at the median (26 phrases, 4 skipped).
- [x] Live voice sample check (2026-11-15): each sample becomes its own voice on the engine (`<session>-v<n>`), speaks one
  known sentence and Prisma hears it back; the share of words is its score (`gpu_voice_score` on the session). The first
  sample is used at once; if it scores under 0.85, later pauses give up to two more and a clearly better one takes over.
  One run: score 0.89, and 86% of the words of that run's dub were heard back.
- [x] Studio separation on the GPU (2026-11-15, `GPU_SEPARATE_URL`, `gpu_engine/sep_engine.py`): 60 s of audio in 11.5-13.8 s
  through the tunnel (1.5 s on the A100, the rest is transfer), against 38.9 s on the laptop CPU; same stems (-40 dB
  difference). Falls back to the CPU on any failure.
- [x] **Streamer Mode** (2026-11-15, spec in STREAMER_MODE.md; reuses the Live pipeline, nothing rebuilt):
  - `/streamer`: profile (`streamers` table), voice recorded once with the consent sentence read aloud, go-live wizard
    (any audio input incl. virtual cables, level meter, service health). `POST /api/streamers`, `.../voice`,
    `.../voice/preview`, `DELETE .../voice`, `GET /api/streamers/health`.
    Also `PATCH /api/streamers/{id}` (name, channel, languages; the handle never changes) and `DELETE /api/streamers/{id}`
    (profile + voice, handle freed). The page has a profile bar (Edit / Exit = forget on this device / Delete), an
    "open by handle" box, and a banner for a stream this device left open (open its console / end it).
  - The recording becomes a Gnani embedding and a GPU voice: cleaned with Demucs on the GPU machine, up to three
    7 s cuts, each transcribed from the exact cut and scored; the best is stored (`ref_path`, `ref_text`, `ref_score`).
    Measured: 17.6 s for the whole request (11.7 s for the GPU voice), score 1.0 on the first cut, previews 1.6-1.9 s.
  - `POST /api/live/sessions` takes `streamer_id` + `voice_mode` (`clone`|`stock`). With `clone` the stored voice goes to
    the engines when the session starts. Measured, Tamil + Bengali, sync mode: 33 of 33 spoken phrases in the streamer's
    voice in each language, from the first phrase; delay stayed 6 s; 87% / 80% of words heard back.
  - A streamer's own mic: speech is real time, YouTube shows it later, so each phrase is due `offset_ms` after it was
    spoken (session `clock` messages let a viewer place `t_speech_ms`; console slider 0-40 s; viewers follow it unless
    they moved their own). The offset is YouTube's delay, so it never grows by itself. Viewers report how late each
    phrase really started (`played` on the watch socket -> `viewer_on_time_pct`). Measured in Edge, offset 8 s, dense
    reel: 30 of 31 phrases arrived before they were due; 77% started within 1 s of their moment, p95 3.2 s late.
    The offset is set by ear; automatic calibration from the embed's sound was not built.
  - `live_clone_needs_streamer`: **off since 15 Nov (the user's decision)**, so `/live` can again copy the voice on the
    stream behind its consent tick (403 without it). On = only a streamer profile clones and the `/live` form is stock only.
    Was: a session without a streamer cannot copy a voice (403). `scripts/live_e2e.py --voice stream` therefore needs `--streamer <id>` now.
  - Not tested: a real microphone with a person, a real OBS -> YouTube broadcast with this flow, a phone.
- [x] Demucs htdemucs on CPU: **40.3 s for 60 s of audio** (Ryzen 7 7435HS, torch 2.15 CPU, measured 2026-11-13). Silero VAD: 3.5 s for a 14 s clip including model load.

## 18. Implementation notes (M2)

- Storage: `db.get_store()` returns `SupabaseStore` when `SUPABASE_*` is set, else `LocalStore` (`data/local_db.json`)
  so the pipeline runs and is tested without a project. Render outputs go to the `renders` bucket (signed URLs) in
  Supabase mode, else are served from `/files/{job_id}/{name}`.
- Audio is numpy + soundfile (pydub needs `audioop`, removed in Python 3.13). Demucs runs in a subprocess
  (`app/studio/demucs_worker.py`) that avoids torchaudio file I/O.
- Cache (`data/cache/<stage>/`), content-addressed and shared across jobs: separate (full.wav hash),
  segment (vocals hash + params), transcribe (clip audio hash + lang + model), translate (lines + lang + glossary +
  model), voice (text + lang + voice + model + sample rate). Edited lines are never overwritten by re-translation.
- Usage counters and warnings are stored in `jobs.stage_timings._usage` / `._warnings`; per-language stage times as
  `"<stage>:<lang>"`; `_total` is the sum of stage times.
- Run a real job without the server: `python -m scripts.dub_file reel.mp4 --langs ta-IN`.

## 19. Status (2026-11-13 night)

- Built: M0-M2 backend, M3 Live backend (assembler, bus, pipeline, WS ingest/watch/chat, metrics), every page in
  section 12 (FRONTEND.md design system v2, GSAP + Lenis), browser-mic ingest on `/live`, OBS overlay.
- Verified offline: 42 backend tests; full site in `MOCK_PROVIDERS` mode with real Demucs/Silero/ffmpeg;
  Playwright screenshots of every page at 390 and 1440 px with no console errors and no horizontal overflow.
- **Not yet verified against real Gnani/LLM** (no keys yet): smoke latencies, Prisma realtime event timing,
  TTS SSE `raw` container format, VC language quality, real Live latency. Run `scripts/smoke.py` first.
- Live latency is `t_first_audio - t_speech_end`, where `t_speech_end` = arrival of Prisma's `processing` event
  minus `x-min-silence-ms` (500). Revisit once real event timing is observed.
- Frontend redesigned (design system v2, see FRONTEND.md): serif headings, voice orb and live bars, floating header, dark footer, lucide icons. Indic text is never split per character.
- Voice visuals with real audio: mic on `/live`, `/voices` and the landing "try your mic"; dubbed audio on `/watch`. Other bars are labelled illustrations.
- Language hues fail CVD checks as a chart palette (te/en too close), so charts use ink bars with a hue dot +
  name label; colour never carries meaning alone.

## 17. Later findings (continues section 16)

- [x] A wrong PC clock stops Live (2026-11-15): the dev laptop's clock fell 5 h 30 min behind, Gnani had renewed its
  certificate that night, and every Gnani connection failed with "certificate is not yet valid" (0 phrases, no dub).
  The console now says to sync the clock. Check `date` against a server's `Date` header before blaming the pipeline.
- [x] GPU machine replaced (2026-11-20): new address and login, and nothing of the engines was on it. Rebuilt from
  `gpu_engine/` (`setup_machine.sh`, a new `voice_engine_live.py`, IndicF5 gated on Hugging Face). Three engine processes
  ran one after another until CUDA MPS was turned on (3 lines at once 3.2 s -> 1.1 s). Same dense reel, voice learned from
  the stream, Tamil + Bengali: 31 of 33 and 32 of 34 spoken phrases in the copied voice, behind p50 0.1-0.3 s / p95 1.8-2.5 s,
  delay 9.5 s, voice step 1.85 s a phrase (first machine: 1.45 s). Separation: 60 s of audio in 4.0-4.8 s.
  A stored voice sample of 15.7 s made lines slow and long (Tamil 9 words -> 18 s of audio, 30% heard back): samples must
  stay near 7 s.
- [x] Voice engine tuned (2026-11-20, same reel, sync mode, real APIs):
  - The library sizes a new line by UTF-8 bytes against the sample's text. A sample transcribed in Latin letters
    (Hinglish, 1 byte a letter) made Indic lines (3 bytes) three times too long: Tamil 9 words -> 18 s, 30% heard back.
    The engine now corrects the speed to letters, the same in every script: 9.0 s and 100%.
  - `speech_cut` counted only loud frames, so a quiet microphone gave a 15.7 s sample. It now counts all speech and
    never returns more than the wanted length + 2 s.
  - Denoising steps, 10 lines heard back by Prisma: 12 steps 905 ms / 97%, 10 steps 744 ms / 97%, 8 steps 601 ms / 96%,
    6 steps 455 ms / 89%. The engines run at 10 (`NFE` in `start_live.sh`). How natural 8 sounds was not judged.
  - Result. Live, voice learned from the stream, Tamil + Bengali: 33 of 33 and 31 of 31 spoken phrases in the copied
    voice, first audio p50 3.1-3.2 s / p95 3.8-3.9 s (before tuning 3.9 / 4.7), behind p50 0.2-0.4 s / p95 1.8-3.5 s,
    voice step 1.2-1.3 s a phrase (before 1.85 s; first machine 1.45 s), video held 9 s.
    Streamer Mode, stored voice, Punjabi + Bengali: 34 of 34 and 29 of 31, first audio p50 3.2-3.3 s, behind p50 0 s /
    p95 1.7-2.8 s.
  - A request through the SSH tunnel costs a median 410 ms although the network round trip is 170 ms; not solved.
- [x] GPU engine made faster (2026-11-21; A100 40 GB; model = IndicF5 DiT 337.1 M parameters + Vocos vocoder 13.6 M):
  - In bf16 one engine keeps the GPU only 39% busy: the time is Python overhead, not GPU work. The library calls the
    network twice per step (with and without the sample and text). `BatchedGuidance` runs both as one batch of two and
    makes the text embedding once per line: 10 steps 742 ms -> 366 ms, GPU 52% busy. In fp32 the two ways agree to
    -37..-49 dB; in bf16 the log-mel distance from the fp32 audio is 0.4-1.2 dB (two-pass bf16: 0.5-0.6 dB).
    `CFG_BATCH=0` restores the library's way. Steps are back at 12 (439 ms; 16 steps 574 ms).
  - Making Opus took 144 ms a line on the GPU machine's CPU. MP3 (VBR, about 39 kbit/s) is the same size, takes 30 ms and
    is closer to the line (0.48 dB against 0.73 dB log-mel). `gpu_voice_format` is now `mp3`.
  - One line from the laptop: 1.33 s -> 0.79 s (engine 0.44 + encode 0.03 + network 0.32); three at once 1.75 s -> 0.97 s.
    The network part is two trips of 157 ms: a 14 KB answer does not fit the first TCP window after idle.
    A tunnel with an interactive session (TCP_NODELAY) cut a small request from 359 to 157 ms but a line not at all.
  - GPU use, engines only, lines as a live session sends them: idle 0% and 13.1 of 40 GB (three engines + Demucs);
    1 language at a phrase every 2.2 s: 11% average, 70% peak; 3 languages: 19% average, 100% peak, 110 W;
    3 languages at a phrase every 1.0 s: 54% average, line still 845 ms at the median (slowest 2.6 s).
  - Gnani speech-to-text (REST and realtime) answered every request with a failure during this work
    ("TRANSCRIPTION_FAILED", also for a clean line made by Gnani's own voice); it answered again at 06:13 UTC on 21 Nov.
  - Live on the faster engine, measured then (same dense reel, sync mode, voice learned from the stream, Tamil + Bengali,
    one run, morning): first audio p50 2.7 s in both languages (20 Nov: 3.1-3.2 s), p95 3.7 s Tamil / 5.3 s Bengali
    (3.9 / 3.8 s; the first three Bengali phrases of the session took 5-8 s); voice step 0.77 s a phrase (1.2-1.3 s);
    30 of 32 and 33 of 35 spoken phrases in the copied voice; the video stayed held at 6 s (the 20 Nov run ended at 9 s);
    dub behind its moment p50 0.3-0.4 s / p95 2.4-2.6 s, 47% of phrases on time.
  - Words heard back by Prisma (`scripts/live_quality.py`), both runs checked in the same hour: this run 74% Tamil /
    72% Bengali, the 20 Nov run (two guidance passes, Opus) 69% / 73%, Gnani's stock Tamil voice in this run 69%.
    So the faster engine is not less clear. On this reel the check reads lower than the 80-89% of earlier reports.


## 20. From event build to product: what is missing (21 Nov 2026)

Checked against the code and the running setup on this date. Nothing here is built; the order is a suggestion.

- [ ] **Accounts.** There is no sign-in. Anyone who reaches the site can start jobs and sessions, see `/voices` and
  `/dashboard`, and open a streamer profile by its handle. Voice profiles are not tied to a person beyond the consent record.
- [ ] **Hosting.** Backend and frontend run on one laptop (ports 8010 and 3000). The GPU engines sit on a shared machine
  behind an SSH tunnel and do not start by themselves after a restart. No domain, no HTTPS, no deploy script.
- [ ] **Data.** Supabase is not configured on the running setup: jobs, sessions and voices live in one local JSON file
  (`LocalStore`, single process), outputs on the local disk.
- [ ] **Speech-to-text has one provider and no fallback.** On 21 Nov 2026 Gnani speech-to-text failed every request
  (REST and realtime, checked several times through one working session) while its voices worked: Live, Studio
  transcription and new voice recordings all stop with it. It answered again at 06:13 UTC the same day. The site's health panel shows "key set", not whether the service answers.
- [ ] **Capacity.** The Gnani account allows one request at a time: enough for one stream. Whether it allows two
  realtime speech-to-text sockets at once is not known. One A100 measured 19% average use for one stream in three languages.
- [ ] **Cost per dubbed minute** is not measured (speech-to-text, translation, voice, GPU hours), so there is no price.
- [ ] **Usage limits and payment.** No per-user limits, no metering beyond the dashboard totals, no billing.
- [ ] **Terms, privacy, takedown.** Consent is recorded and voices are deletable, but there are no terms or privacy
  pages and no way for a third party to report a misused voice or video.
- [ ] **Never tested:** a person at a real microphone over a long session, a real YouTube Live broadcast with outside
  viewers, a phone on a mobile network, word error rate on ground-truth clips, how close the copied voice sounds to
  the speaker (needs listeners).
- [ ] **Monitoring.** No error tracking or alerts; a failure is seen only when someone looks at the console.
- [x] **Why "on time" sat at 45-70% in sync mode** (2026-11-21). "On time" = the dub starts within 0.25 s of the video
  moment its phrase was spoken at. One run on the dense reel, Tamil: 45% within 0.25 s, 71% within 1 s, 87% within 2 s;
  a user session in Punjabi: 56% / 81% / 94%. Of 17 late Tamil phrases, 4 had audio that arrived late and 13 had audio
  ready in time but waited for the dub before them. The hold is not the cause: replaying the run with a 7 s hold instead
  of 6 s leaves Tamil at 45%.
  - Cause found: the moment itself was wrong. The tail of a line was counted back from its end at the speaker's pace,
    and 10 of 36 phrases were stamped as starting before the phrase before them had ended (by up to 1.3 s), so their
    dub was due while the earlier dub was still playing.
  - `live_stamp_fix` (on): a tail starts when its first word showed up in a partial (`Phraser.tail_start`), and no
    phrase starts before the one before it ended. Replay of the same run with the recorded audio and corrected stamps
    (an estimate: speed-up decisions would change in a real run): Tamil 45% -> 61% on time, 71% -> 81% within 1 s,
    p90 2.1 s -> 1.2 s; Bengali 48% -> 67%, 70% -> 82%. **Not yet measured in a live run.**
  - What is left is real: on dense speech the dubbed phrase is longer than its slot even at the 1.3x limit (19 of 31
    Tamil phrases were at the limit), because the word budget allows 1.15x the speaker's time when in step and a
    speaker who does not pause leaves no room. Not changed yet.
