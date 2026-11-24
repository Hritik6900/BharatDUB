# EXP-019: Hosted stock voice vs copied voice (clarity, brightness)

- **Date:** 2026-11-21
- **Status:** partial
- **Decision:** none

## Question

The founder found the hosted output better than the GPU engine's. Part by part, what does the GPU engine's copied voice
lack against the hosted stock voice?

## Hypothesis

Not recorded; implied: the copied voice is less clear (fewer words heard back) or slower.

## Setup

- Language: Punjabi, 16 lines each voice.
- Voices: hosted stock voice; IndicF5 on our GPU in the copied voice of a Hindi speaker (recorded sample); IndicF5 at 32
  steps instead of 12; IndicF5 with the native Punjabi speaker's sample published with IndicF5.
- Engines on the A100 GPU VM (address in `docs/v1/NEEDS_APPROVAL.md`) through the tunnel. One run per voice.

## Metrics

- **Words heard back** ([GLOSSARY](../GLOSSARY.md)): Prisma hears each line back.
- Pace: ms a word. Time to make a line.
- Output sample rate, and brightness: share of the sound energy above 4 kHz.

## Results

All **measured**, 2026-11-21, 16 Punjabi lines each, one run (SPEC.md section 21 "GPU engine against the hosted
services", Voice).

| Voice | Words heard back | ms a word | Time to make | Sample rate | Above 4 kHz |
|---|---|---|---|---|---|
| Hosted stock voice | 94% | 345 | 741 ms | 44.1 kHz | 3.2% |
| IndicF5, copied voice (Hindi speaker) | 93% | 370 | 454 ms | 24 kHz | 0.6% |
| IndicF5, 32 steps | 94% | not given | 2.5x the time | 24 kHz (unconfirmed) | 0.7% |
| IndicF5, native Punjabi sample | 95% | 330 | 457 ms | 24 kHz (unconfirmed) | 2.9% |

- The recorded sample itself has 0.9% above 4 kHz, its 16 kHz cut 0.5%: the engine copies the sound of the microphone
  with the voice. **measured**.

## Caveats

- One run, 16 lines, one language.
- Only Punjabi and Marathi samples come with the model.
- Accent and naturalness were not measured; they need ears (status: partial).
- Brightness above 4 kHz is a proxy for "duller"; no listener judged it.

## Decision taken

No ADR. Words are as clear; the copied voice is duller because its sample is. More steps give no gain. The native-speaker
sample was not built into the product.

## Links

- [SPEC.md](../../../SPEC.md) section 21 ("GPU engine against the hosted services, part by part")
- Commits: `3a20c06` (voice compared with the hosted stock voice line by line)
- Related: [EXP-012](EXP-012-clone-similarity.md), [EXP-018](EXP-018-prisma-vs-whisper-hard-audio.md),
  [ADR-0010](../adr/0010-indicf5-own-gpu-voice.md)
