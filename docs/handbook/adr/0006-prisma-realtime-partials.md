# ADR-0006: Hosted Prisma realtime STT with partials; phrases cut from stable text; source language pinned

- **Status:** accepted
- **Date:** 2026-11-13
- **Superseded by:** — (in the GPU engine the order of hearing is set by ADR-0015 and ADR-0016)

## Context

Live needs text of what the streamer said as early as possible. The provider docs said Prisma's realtime socket
sends **no partial transcripts**: one final per utterance (`../../../SPEC.md` section 6.2). Waiting for a whole
utterance put the first dubbed audio far behind the speaker. First real run on 13 Nov, stock voices, 3 languages,
whole utterances: first audio p50 3.6 s / p95 4.7 s (**measured**, SPEC section 16, dense 24.9 s reel in real
time, `LIVE_TEST_REPORT.md`). Those figures used "final arrival - 500 ms" as the end of speech, which the real
`speech_end` later showed to be 0.3-0.6 s too kind (SPEC section 16).

Also on 13 Nov: `indic-auto` over game sound produced Bengali/Kannada garbage, and `hi-IN,en-IN` was not accepted
by the realtime socket (SPEC section 16).

## Options considered

| Option | Outcome |
|---|---|
| Whole utterances (one final each), `LIVE_PARTIALS=false` | kept as the fallback switch; slower, as above |
| Partials through an undocumented upgrade header `x-partials: true` (found 13 Nov) | **chosen** |
| Language auto-detect (`indic-auto`) | rejected: wrong languages over game sound (13 Nov) |
| Our own speech-to-text on the GPU | came later as a second engine (ADR-0015); measured weaker on hard audio (ADR-0016) |

## Decision

- Realtime STT on hosted Prisma `prisma-v3.0` with `x-partials: true` and `x-partial-interval-ms` 300. Events
  `partial_transcript` (with `stable_text`), `speech_end`, `final_transcript` (SPEC section 16).
- `Phraser` in `live/assembler.py` cuts phrases of 6-12 words at a clause boundary from `stable_text`, so
  translation and voice start before the speaker pauses; the final supplies only the tail.
- Source language pinned per session (`src_lang`, default `hi-IN`).

## Consequences

### Good

- After phrase chunking (13 Nov, same reel, 4 languages, one viewer language, stock voice): end of phrase to first
  audio p50 2.3 s / p95 3.6 s; first word of a phrase to first audio p50 3.4 s / p95 5.2 s (**measured**, SPEC
  section 16, one run).
- On 21 Nov Prisma's partials gave longer phrases than our Whisper (8 source words against 7) and far better key
  words on hard audio (ADR-0016).

### Bad

- It rests on an undocumented header; a vendor change could remove it without notice.
- Phrase cuts caused later timing bugs: phrases stamped before the previous one ended (fixed 21 Nov, ADR-0009),
  a phrase cut one word before its sentence ended, a tail repeating words just dubbed (4 of 270 lines on a real
  stream, `93b5c45`).
- Sources other than Hindi/Hinglish need a different pin; not measured.
- The hosted account allows one request at a time and one stream (SPEC section 20, "Capacity").

## Evidence

- Experiments: [EXP-001](../experiments/EXP-001-gnani-smoke-latency.md), [EXP-003](../experiments/EXP-003-live-stock-first-audio.md)
- Commits: `66de705`/`7a3279f` (smoke, missing `processing` event), `751375f`/`a6e9d03` (pin the source language),
  `2188ad3`/`4c3bc2b` (phrases from partials), `93b5c45` (tail repeat fix)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 6.2, 9, 16; [`LIVE_TEST_REPORT.md`](../../../LIVE_TEST_REPORT.md)
