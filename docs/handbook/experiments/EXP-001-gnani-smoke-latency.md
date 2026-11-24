# EXP-001: Hosted provider smoke latencies and account concurrency (=1)

- **Date:** 2026-11-13
- **Status:** done
- **Decision:** ADR-0007 ([../adr/0007-hosted-llm-translation.md](../adr/0007-hosted-llm-translation.md))

## Question

How fast does each hosted provider answer on the real API (speech-to-text, voices, voice copy, translation), and how
many requests does the hosted speech account allow at once?

## Hypothesis

Not recorded; implied: the providers answer fast enough for a Live budget of 3-5 s, and the account limit of
"1 active request" shown in the provider's docs may be higher on our account (SPEC section 16 listed it as an open
question).

## Setup

- Data: a ~5 s Hindi clip for the speech and voice calls; a 3-line batch and single live chunks for translation;
  a 9.8 s synthetic sample for the voice-copy embedding.
- Providers: Gnani Prisma `prisma-v3.0` (REST and realtime), Timbre `timbre-v2.5` (REST and SSE), `vachana-vc-v1`;
  Gemini through its OpenAI-compatible endpoint (`gemini-3.5-flash`, `LLM_REASONING_EFFORT=none`).
- Tool: `backend/scripts/smoke.py` on the dev laptop. One run each.
- Concurrency: three voice calls sent at the same moment.

## Metrics

- Latency of one call, wall clock from the laptop (TTS REST: whole file; SSE: first chunk).
- STT realtime: time from the end of the audio to the final transcript.
- Concurrency: how many of three simultaneous calls were refused with HTTP 429.

## Results

All **measured**, 2026-11-13, one run each unless a range is given (SPEC.md section 16).

| Call | Result |
|---|---|
| TTS REST (whole file) | 1.2 s |
| TTS SSE, first chunk | 0.18-0.24 s |
| STT REST | 0.59 s |
| STT realtime, final after audio ends | ~0.76 s (server `latency` field ~170 ms) |
| Voice-copy embedding from a 9.8 s sample | 1.4 s |
| Translation, 3-line batch (`gemini-3.5-flash`, thinking off) | 1.4-2.2 s |
| Translation, one live chunk | ~1.5 s |
| Translation with thinking on | 4-5 s, reply truncated |
| Stock voice, five more languages (Kannada, Malayalam, Marathi, Gujarati, Punjabi), one line each | 1.2-3.7 s |
| Three TTS calls at once | 2 of 3 got 429 "Only 1 active request is allowed at a time" |

Other findings the same day: the realtime socket sends no `processing` event (only `connected`, `speech_start`,
`transcript`); `gemini-3.5-flash-lite` returned the Hinglish untranslated; prompts had to demand native script.

## Caveats

- One run per call, from one laptop, at one time of day. SPEC section 16 later found provider speed varies through
  the day (a 7-word Tamil phrase took 0.9 s in one hour and 2.5 s in another, 2026-11-14).
- The copied-voice check was an intelligibility check (Prisma heard each cloned line back with the same words, one
  line each in Tamil, Hindi and English, synthetic source voice), not a listening test.
- The early end-of-speech estimate (final arrival - 500 ms) was later found 0.3-0.6 s too kind (see EXP-003).

## Decision taken

- Translation runs on hosted Gemini (no hosted Evon endpoint on the speech provider's dashboard) with
  `LLM_REASONING_EFFORT=none` (ADR-0007).
- All hosted speech calls go through one process-wide gate, `GNANI_MAX_CONCURRENCY=1`; this limit later shaped the
  Live voice queue (EXP-004) and the move to our own GPU voice (EXP-007, ADR-0010).

## Links

- [SPEC.md](../../../SPEC.md) section 16 (entries dated 2026-11-13: smoke latencies, LLM, VC on the real API,
  account concurrency, all ten languages)
- Commits: `227f031` (providers, smoke script), `66de705` (smoke against the real API), `ee932e8` (Gemini
  reasoning-effort setting, native-script prompts)
- Related: [EXP-003](EXP-003-live-stock-first-audio.md), [EXP-005](EXP-005-live-llm-bench.md),
  [EXP-007](EXP-007-copied-voice-hosted-vs-gpu.md), [ADR-0006](../adr/0006-prisma-realtime-partials.md)
