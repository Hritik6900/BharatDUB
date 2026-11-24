# Product

What Bharat Dub does, for whom, how far it is built, and what has never been tested.
Dated 2026-11-25. The v1 documents spell the name "BharatDb"; it is the same product.

Every number below names its source and is labelled **measured**, **estimate** or **target**.
Definitions of the terms: [GLOSSARY.md](GLOSSARY.md).

## 1. What it does

Bharat Dub dubs Hindi and Hinglish speech into other Indian languages and English, in the speaker's own copied
voice where the speaker consented, with captions. One website, one backend, one provider layer, one voice profile.

| Mode | Route | What the user gets | Speed target (SPEC section 1) |
|---|---|---|---|
| **Studio** | `/studio`, `/studio/[jobId]` | Upload a video of up to 3 min; it comes back dubbed (MP4 + SRT), background music kept, in a copied or stock voice | 60 s reel in 2-3 min (**target**) |
| **Live** | `/live` (console), `/watch/[id]` (viewer) | A YouTube Live stream in Hindi/Hinglish; viewers pick a language and hear the dub with captions; viewer chat is translated back | 3-5 s behind the speaker (**target**) |
| **Streamer** | `/streamer` | A streamer records their voice once (consent sentence read aloud) and goes live; the dub is in their voice from the first sentence | as Live |
| Shared | `/voices`, `/glossary`, `/dashboard`, `/overlay/[id]` | voice profiles (with consent, deletable), words never translated, usage and latency, OBS overlay for translated chat | - |

v1 adds `/health` (status), `/metrics-ui` (numbers from the trace), `/studio/calibrate` and `/listen-test`, each
behind a flag ([ARCHITECTURE.md](ARCHITECTURE.md#flags)).

Every AI output carries an "AI-dubbed" label (SPEC section 15). See [SECURITY_AND_CONSENT.md](SECURITY_AND_CONSENT.md).

## 2. Users

| User | What they use | Source |
|---|---|---|
| Creators (Reels, Shorts, YouTube) | Studio | SPEC section 1 |
| Streamers (YouTube Live, OBS) | Live, Streamer Mode, overlay | SPEC section 1, `STREAMER_MODE.md` |
| Viewers | `/watch/[id]`: language, captions, sync slider, chat | SPEC section 9 |
| Tournament organisers (gaming events) | Live for a broadcast in several languages | named as a target group in the handbook plan; no feature is built for them specifically (unconfirmed) |

SPEC section 15 rules out dubbing third-party broadcasts (sports, news) in this version.

## 3. Languages

Ten languages: Hindi, English, Tamil, Telugu, Kannada, Malayalam, Marathi, Punjabi, Bengali, Gujarati (SPEC
section 16, 13 Nov 2026). Studio offers all ten (Hindi for non-Hindi videos); Live offers the nine non-Hindi ones.
The source language of a Live session is pinned (default `hi-IN`).

Limits that come from the models ([MODELS.md](MODELS.md)):

- Our GPU speech-to-text hears Hindi and Hinglish only. Other source languages go to the hosted service.
- Our copied voice (IndicF5) has no English. English is spoken by a hosted voice (stock or hosted copy).
- Most measurement is Tamil, Bengali and Punjabi. Kannada, Malayalam, Marathi, Gujarati and Punjabi were each
  checked once on the real API on 13 Nov 2026 (SPEC section 16).

## 4. The two engines

A session or job picks its engine with the "Engine" button (since 21 Nov 2026, `31673b9`).

| | Standard (`cloud`, default) | GPU (`gpu`) |
|---|---|---|
| Speech-to-text | hosted Prisma | hosted Prisma first, our Whisper behind it (`gpu_stt_first`, `3a20c06`) |
| Translation | hosted Gemini | our Gemma 4 E4B first, Gemini behind it |
| Copied voice, Indian languages | IndicF5 on our GPU when configured, else hosted clone | IndicF5 with the short-line guard |
| Stock voices, English | hosted Timbre | hosted Timbre |

Source: SPEC section 21, `docs/v1/DISCOVERY.md` section 2. Details: [ARCHITECTURE.md](ARCHITECTURE.md#provider-layer).

## 5. Current status (25 Nov 2026)

- **v0** is the product people use: branch `main`, frozen at tag `v0-baseline` (`80c36d8`, 22 Nov 2026), folder
  `Desktop\BharatDUB`, ports 3000 (web) and 8010 (backend). It was not changed by v1.
- **v1 and v1.1** are on branch `v1` (folder `Desktop\BharatDUB-v1`, ports 3100 and 8110). Every new behaviour is
  behind a flag that is off by default; with every flag off v1 behaves as v0. v1 was built on 23 Nov (`92638c1` ..
  `01c9728`), v1.1 on 24-25 Nov (closed by `e4944fd`). Tests: 311 pass, 1 skipped (`docs/v1/V1_1_SUMMARY.md`).
- **Where it runs:** one Windows laptop (backend and website) and one borrowed A100 40 GB VM (model servers),
  reached by SSH tunnels. No domain, no HTTPS, no accounts. See [ARCHITECTURE.md](ARCHITECTURE.md#deployment).

## 6. Real vs planned

| State | What |
|---|---|
| **Built and measured** | Studio pipeline (10 stages, cache, review editor); Live with sync mode and hold; Streamer Mode with recorded voice; copied voice on our GPU (IndicF5, 3 processes, MPS); all-GPU engine (Whisper + Gemma); Studio HQ (takes, judge, review); breaker + degrade ladder (with a relay standing in for a stall); dense-speech budget; English single voice; pitch recording kit (one example) |
| **Built, not measured** | Postgres store (`V1_STORE=postgres`, never run against a database); Docker compose files (never run); backup script (syntax-checked only); tunnel watchdog (not run); deploy kit for new model servers (stubs only, never on Linux); batching voice server, Maya 2, Indic Transcribe, big translation model, QA server's Whisper (no real model loaded); live back-check (no scorer); number normaliser on real numbers; calibration page (no labels); listening test (no pairs) |
| **Planned** | backend on the GPU machine (NEEDS_APPROVAL items 1-3); QA server on CPU (item 4); diarization (item 7); domain and HTTPS (item 13); backup bucket (item 15); cost per minute (item 23) |
| **Not built** | accounts / sign-in; hosting with a deploy script; billing and per-user limits; terms and privacy pages; a way to report a misused voice or video (takedown); error tracking and alerts (SPEC section 20) |

The full ordered list of what waits: [ROADMAP.md](ROADMAP.md) and `../v1/NEEDS_APPROVAL.md`.

## 7. Headline numbers

All from the sources named; full tables in [RESULTS.md](RESULTS.md).

| What | Number | Label | Source, date, conditions |
|---|---|---|---|
| Live first audio p50 / p95, all-GPU, backend on the GPU machine | 1.8 s / 2.1 s | measured | SPEC section 21, 21 Nov 2026, dense reel six loops, Tamil + Bengali, one run |
| Live first audio p50, through the laptop tunnel, v1 flags off | 2.34 s (2.27-2.40) | measured | `docs/v1/EVAL_REPORT.md` section 1.1, 23 Nov 2026, 3 runs |
| Live within 1 s of the video moment, dense speech, flags off / with budget | 86.5% / 92.3% | measured | `docs/v1/LIVE_DENSE_REPORT.md` via V1_1_SUMMARY section 2.1, 24 Nov 2026, 5 runs a setting |
| Real 67-minute stream, all-GPU, within 0.25 / 1 / 2 s | 81% / 97% / 98% | measured | SPEC section 21, 21 Nov 2026, 1363 phrases, Punjabi, one stream |
| Studio HQ words heard back / standard | 95.9% / 90.6% | measured | V1_1_SUMMARY section 2.5, 25 Nov 2026 rerun, three videos, 76 lines |
| Studio words heard back | 96% | target | `docs/v1/ARCHITECTURE.md` (not reached) |
| Live first audio p50 | 1.8 s | target | `docs/v1/ARCHITECTURE.md` (not reached through the tunnel) |

## 8. Never tested

From SPEC section 20 and the v1 reports; each is a gap, not a known failure.

- A person at a real microphone over a long session.
- A real YouTube Live broadcast with outside viewers (only uploaded videos and the user's own streams were used).
- A phone on a mobile network.
- Word error rate on ground-truth clips (`backend/eval/clips/` is empty, `docs/v1/DISCOVERY.md` section 5).
- How close the copied voice sounds to the speaker, by listeners (no listening test has ratings).
- A long dense recording (only one 24.9 s reel exists, NEEDS_APPROVAL item 20).
- A male speaker with the matched stock voice (NEEDS_APPROVAL item 19).
- Two streams at once on one GPU (one test run: on-time fell, SPEC section 21).
- A VM restart: "warm and green in 5 minutes" (`docs/v1/EVAL_REPORT.md`, target not measured).
- The restore from backup (`docs/v1/RUNBOOK.md` section 7, not rehearsed).

Decided in [ADR-0001](adr/0001-cascaded-pipeline.md), [ADR-0013](adr/0013-best-provider-per-capability.md),
[ADR-0014](adr/0014-two-engines-per-session.md), [ADR-0018](adr/0018-v1-beside-v0.md).
