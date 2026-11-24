# EXP-003: Live end to end, stock voices; phrase chunking from partials

- **Date:** 2026-11-13
- **Status:** done
- **Decision:** ADR-0006 ([../adr/0006-prisma-realtime-partials.md](../adr/0006-prisma-realtime-partials.md))

## Question

How long after a speaker finishes does the first dubbed audio leave the server, on the real APIs, and how much does
cutting phrases from realtime partials (instead of waiting for the whole utterance) save?

## Hypothesis

Not recorded; implied: starting translation and voice on stable partial text, before the speaker pauses, cuts first
audio well below the whole-utterance figure.

## Setup

- Data: the dense 24.9 s Hindi reel (one fast speaker, about 4.5 words a second, no pauses) replayed at real-time
  speed through the running backend (`scripts/live_e2e.py`).
- Providers: Prisma realtime (`prisma-v3.0`), Gemini, Timbre stock voices; later runs with the undocumented header
  `x-partials: true` (`x-partial-interval-ms` 300) and the `Phraser` (6-12 words at a clause boundary).
- Source language pinned to `hi-IN` (`indic-auto` over game sound produced Bengali/Kannada lines).
- Backend on the laptop, all hosted. One run per row.

## Metrics

- **First audio**: end of the phrase (or utterance) to the first dubbed audio leaving the server
  ([GLOSSARY](../GLOSSARY.md)). p50/p95 over the phrases of the run.
- "From first word": the same, measured from the first word of the phrase.
- End of speech: first `final arrival - 500 ms` (estimate); from the partials run on, the `speech_end` event or the
  partial that first showed the phrase's last word minus 600 ms (estimate for phrases).

## Results

All **measured**, 2026-11-13, one run each (SPEC.md section 16).

| Run | First audio p50 / p95 |
|---|---|
| Whole utterances, stock, 3 languages | 3.6 s / 4.7 s |
| Whole utterances, cloned voice (hosted), 1 language | 4.6 s / 5.4 s |
| Phrases from partials, stock, 4 languages, 1 viewer language | 2.3 s / 3.6 s (from first word 3.4 s / 5.2 s) |
| Phrases, voice learned from the stream | 4.1 s / 4.8 s (from first word 5.0 s / 6.6 s) |

- The voice learned from the stream was ready 33-37 s after the stream started (hosted clone, 12 s of speech).
- Hosted clone lines took 1.9-3.5 s each and are not streamed (stock: ~0.5 s to first chunk).

## Caveats

- **The first-row numbers are too kind by about 0.3-0.6 s**: they used final arrival - 500 ms as end of speech,
  and the real `speech_end` event showed speech ends earlier (SPEC section 16).
- First audio is not what a viewer hears; the next day showed the phrase run's heard delay at 7.8 s p50 (EXP-004).
- One reel, one speaker, no person at a microphone, sessions no longer than 82 s.

## Decision taken

Live cuts phrases from Prisma's `stable_text` (`LIVE_PARTIALS`, default on); source language pinned per session; audio
made only for languages a viewer is tuned to; phrases over 8 s late not spoken (ADR-0006, ADR-0008).

## Links

- [SPEC.md](../../../SPEC.md) section 16 (Live end to end 2026-11-13; realtime partials; latency after phrase chunking)
- [LIVE_TEST_REPORT.md](../../../LIVE_TEST_REPORT.md) "Read this first", "What changed on 13 and 14 Nov"
- Commits: `a7e7bb6` (live e2e scripts and report), `a7f75b3` (audio only for heard languages, skip >8 s),
  `2188ad3` (phrases from partials, real speech-end timing)
- Related: [EXP-001](EXP-001-gnani-smoke-latency.md), [EXP-004](EXP-004-heard-vs-first-audio.md),
  [ADR-0008](../adr/0008-heard-delay-pacing.md)
