# Streamer Mode: build spec

Read SPEC.md and FRONTEND.md first. This adds the streamer-side product to Bharat Dub by **reusing the Live
pipeline that already works** (`backend/app/live/`). Nothing is rebuilt. Existing routes, tests (67) and
behaviour stay; every new behaviour sits behind a setting.

## 1. Product

A streamer makes a profile, records their voice once with consent, and goes live on YouTube with OBS as usual.
Their voice (mic, or a virtual cable carrying OBS audio for demos) goes into our console. Viewers open our
page: the streamer's YouTube live video (muted) + the dub in the streamer's own voice + captions, lined up
with the video. Viewers chat in their language; the streamer sees it translated. One pipeline per stream.

## 2. What already exists and is reused as it is

| Need | Already there |
|---|---|
| Realtime STT, phrase cutting (6-12 words) | `live/pipeline.py`, `live/assembler.py` (`Phraser`) |
| Gnani one-at-a-time turn, merging waiting phrases, 1.3x fit, skip when late | `live/pipeline.py` |
| Word limit for the translator, condensed lines when behind | `live_length_budget`, `live_brief` |
| Copied voice on the GPU (3 engine processes), check of every voice sample | `providers/tts_gpu.py`, `gpu_engine/` |
| Captions, audio bus, chat, OBS overlay, viewer page, delay badge | `/watch/[id]`, `/overlay/[id]`, `live/chat.py` |
| Studio Demucs on the GPU | `GPU_SEPARATE_URL`, `gpu_engine/sep_engine.py` |

Do not write a second phraser, limiter, audio bus or player. Do not add binary frames or an AudioWorklet.

## 3. Facts measured on this project (design around them)

- Gnani account: one request at a time. A cloned line from Gnani takes 2-3.5 s: live it reached 5 of 21 phrases.
- GPU engine (IndicF5, A100 in Seoul, SSH tunnel): one line 0.9 s on the machine, 1.2-1.7 s from the laptop;
  three lines at once 1.2 s with three processes. Live: 31 of 32 phrases in the copied voice.
- The engine reads only a language's own letters (English words must be written in the target script), copies
  the pace of its sample (the sample's text must be exactly what is in the audio), and loses words when asked
  to speak faster itself (use `atempo` afterwards). English as a target language stays on Gnani.
- Phrases shorter than about 6 words cost more than they save (about 1.3 s fixed per Gnani call) and once took
  the heard delay from 3.4 s to 7.8 s. Keep 6-12 words.
- Best heard delay, stock voice, one language: p50 3.4 s. Gnani and Gemini are slower in the afternoon.
- A live YouTube embed ignores a seek backwards; pausing works and it resumes behind by as long as it waited.
- The tunnel drops; `gpu_engine/tunnel.ps1` reconnects and the pipeline returns to the GPU voice by itself.

## 4. What is new

### A. Streamer profile and voice (consent first)
- Store: `streamers {id, handle, display_name, youtube_channel, default_langs, voice_profile_id}`.
  `voice_profiles` gains `sample_path`, `sample_text`, `sample_score` (additive).
- `/streamer/onboarding`: handle, name, YouTube channel, languages. Voice step: record 20-30 s in the browser
  (or upload), the consent sentence is read aloud and `consent_at` stored. No consent, no profile (HTTP 403).
- From the recording: Gnani embedding (Studio, English, fallback) and a GPU sample: the best 7 s
  (`speech_cut`), transcribed by Prisma from that exact cut, scored with the existing check; try up to three
  cuts and keep the best. If `GPU_SEPARATE_URL` is set, clean the cut with Demucs first (helps recordings and
  virtual-cable input). Preview: one line in Tamil and one in Bengali. Delete anytime.

### B. Sessions that start with the voice
- `POST /api/live/sessions` accepts `streamer_id` and `voice_mode: stock|clone`. With `clone`, the stored
  sample is sent to the GPU engines when the session starts, so the **first phrase** is already in the
  streamer's voice (no learning time). Engines down: Gnani clone for the first language, stock for the rest.
- `voice_mode: stock` never clones.

### C. Go-live wizard and console (`/streamer`)
- Input: list all audio inputs (virtual ones too) with a level meter; `getUserMedia` with echo cancellation,
  noise suppression and auto gain OFF. Card "Demo with a recording": VB-Cable + OBS "Monitor and Output".
- YouTube live video id with embed preview, languages (GPU languages + English), voice mode.
- Health before start, all measured live: Prisma, Gemini, Gnani TTS, each GPU engine, the voice's score.
- Console: reuse `/live` (transcript, captions, delay, chat, overlay link, viewer link + QR, Stop).

### D. Sync for a streamer's own mic (the one real gap)
Mic audio is real time; YouTube shows it N seconds later. So the dub is early, and has to wait.
- Audio and captions already carry `t_speech_ms`. Add a `clock` message (session time, every second) so a
  viewer can place `t_speech_ms + offset_ms` on its own clock; play each phrase then, or at once if late.
- `offset_ms` = the stream's YouTube latency. Session default set by the streamer, viewer slider from
  -5 s to +40 s saved per viewer. Tell streamers to use YouTube latency **Low** (about 5-10 s): Normal
  (15-30 s) works but feels slow, Ultra-low is too short for a 4 s dub.
- Calibration in the console: the console plays the live video's embed and captures its own tab (already
  built). It lines up the loudness of the mic with the loudness of the embed over 20 s and proposes the
  offset; the streamer confirms. If that is not reliable in testing, keep a manual "set it by ear" slider.
- The video-time sync that exists (`media_s`) stays for "the video on this page".

### E. Safety rule for the old "any stream" mode
Cloning needs a streamer profile with consent. A session without `streamer_id` uses stock voices only; the
"copy the voice on this stream" option is removed from `/live`. Old tests are updated, not deleted.

## 5. Phases (each ends with: all tests, one real run with numbers, a commit)

| # | Phase | Done when |
|---|---|---|
| 1 | Profile + voice onboarding (A) | A recorded voice has a score, previews in Tamil and Bengali, and can be deleted |
| 2 | Sessions with the stored voice (B) + wizard and input devices (C) | A replayed session: first spoken phrase is in the copied voice; engines-down run falls back cleanly |
| 3 | Offset sync + calibration (D) | Viewer page on a real YouTube live: dub starts within 1 s of the video moment for 80% of phrases |
| 4 | Safety rule (E) + health panel | No session without a consented streamer can clone; health shows every provider |
| 5 | `eval/replay_live.py`, README, demo rehearsal | Numbers in `eval/results.csv`, phone demo: QR -> viewer -> Tamil -> chat round trip |

Stop and report only when a phase misses its "done when".

## 6. Acceptance (set from what was measured, on normal-paced speech)

- Copied voice from the first phrase, on every phrase, for GPU languages while the engines are up.
- Phrase end to heard: p50 <= 4.0 s, p95 <= 6.5 s, one language. Report the real numbers either way.
- After calibration, 80% of phrases start within 1 s of their video moment (viewer-reported).
- Engines or tunnel down mid-stream: no silence, stock voice within one phrase, back to the copied voice
  when they return.
- Never show an unmeasured number. No secrets in logs or the browser. Timeout, one retry, visible fallback
  on every external call.

## 7. Not in this build

`/live-now`, `/@handle`, recap pages, 30-minute soak, a second pipeline package, binary frames, AudioWorklet,
voice conversion on Gnani stock audio, translation on the GPU, moving the backend to the GPU machine
(Seoul to Gnani in India is not a clear win; measure before deciding).
