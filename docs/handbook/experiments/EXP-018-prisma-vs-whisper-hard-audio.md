# EXP-018: Prisma vs Whisper STT on the hard set; hold-back; bigger Whisper

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** ADR-0016 ([../adr/0016-hosted-stt-first.md](../adr/0016-hosted-stt-first.md))

Re-measured in v1 on 2026-11-23 (docs/v1/EVAL_REPORT.md section 3).

## Question

On the founder's quiz-class stream the GPU speech-to-text misheard subject words, and the translation carried them into
the dub. Is a bigger Whisper better, is the loss in the model or in the live cutting, and how does hosted Prisma compare?

## Hypothesis

Not recorded; implied: a bigger model hears more key words; or the live phrase cutting settles half-heard words too
early.

## Setup

- Test set: 24 class and stream lines with 80 key words, spoken by two hosted stock voices; clean, and "hard" (15%
  faster, a room's echo, noise 10 dB under the voice). Made speech, not a real teacher.
- Models: Whisper-Hindi2Hinglish-Apex (the GPU engine's), Whisper large-v3-turbo, large-v3; hosted Prisma.
- Live cutting test: the hard set streamed live through the GPU engine's partials; hold-back of the last 1 / 2 / 3
  agreed words; beam 5 (`STT_HOLD_BACK`, `STT_BEAM` in `stt_engine.py`).
- Session cost test: the clean dense 24.9 s Hindi reel, Tamil + Punjabi, one run each, GPU model vs Prisma hearing.
- v1 re-measure: `python -m eval.v1.stt`, clean once, hard three times with new noise each run; backend on the laptop.

## Metrics

- Key words right, out of 80.
- Decode time per utterance.
- Session: **on time** within 1 / 2 s, phrases at the 1.3x limit, **first audio** p50, **words heard back**
  ([GLOSSARY](../GLOSSARY.md)).

## Results

Models, **measured**, 2026-11-21, one run (SPEC.md section 21 "speech-to-text on hard audio"):

| Model | Clean | Hard | Decode time |
|---|---|---|---|
| Whisper-Hindi2Hinglish-Apex | 69 | 48 | 87 ms |
| Whisper large-v3-turbo | 67 | 40 | not given |
| Whisper large-v3 | 65 | 50 | 388 ms |

Live cutting on the hard set, **measured**: whole-utterance decodes had 49 of 80, settled words (phrases are cut from
them) 41. Hold back 1 word: 46 (six words settled 0.1 s later); 2 words: 47 (0.35 s later); 3 words: 48 (0.65 s later).

Hosted vs GPU, **measured**, 2026-11-21, one run (SPEC section 21 "GPU engine against the hosted services"):

| Provider | Clean | Hard |
|---|---|---|
| Hosted Prisma | 77 | 73 |
| Our GPU model | 70 | 49 |

v1 re-measure, **measured**, 2026-11-23 (docs/v1/EVAL_REPORT.md section 3):

| Provider | Clean (1 run) | Hard, mean of 3 (range) |
|---|---|---|
| Hosted Prisma | 77 of 80 | 71.3 of 80 (71-72) |
| Our Whisper (port 9030) | 70 of 80 | 52 of 80 (50-55) |

Cost of Prisma hearing first in a session, **measured**, one run each, GPU model -> Prisma:

| Metric | GPU model | Prisma first |
|---|---|---|
| Within 1 s | 95% | 72% |
| Within 2 s | 99% | 88% |
| At the 1.3x limit | 43 of about 150 | 70 |
| First audio p50 | 2.5 s | 2.3 s |
| Words heard back, Tamil / Punjabi | 81 / 78% | 80 / 77% |

Prisma's partials give longer phrases (8 source words against 7).

Tried and not kept, **measured**: the previous utterance as context (stream finals 49 -> 45); telling the translator
the transcript may hold misheard words (English key words 49 -> 49 of 76).

## Caveats

- The test voices are the hosted provider's own stock voices, which may favour Prisma; the hard-audio gap is far larger
  than that could explain (SPEC).
- One run per v0 arm; the v1 harness makes its own noise, so 73/49 and 71.3/52 are close, not identical.
- The session cost was measured on clean audio only; a session on hard audio, where Prisma should gain, was not run.

## Decision taken

The GPU engine holds one word back and decodes with beam 5. Hosted Prisma hears first with our model behind it
(`gpu_stt_first` = hosted; `gpu` = nothing hosted in the path) (ADR-0016). v1's re-measure confirmed the order.

## Links

- [SPEC.md](../../../SPEC.md) section 21 ("GPU engine, speech-to-text on hard audio"; "GPU engine against the hosted
  services, part by part")
- [docs/v1/EVAL_REPORT.md](../../v1/EVAL_REPORT.md) section 3
- Commits: `be7540b` (hold-back, beam 5), `3a20c06` (hosted hears first), `8608b97` (v1 eval harness and report)
- Related: [EXP-016](EXP-016-real-stream-67min.md), [EXP-019](EXP-019-hosted-stock-vs-copied-voice.md),
  [ADR-0015](../adr/0015-gpu-stt-translation.md)
