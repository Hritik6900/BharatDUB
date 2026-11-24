# EXP-017: Indic-Mio vs IndicF5; short-line guard

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** ADR-0017 ([../adr/0017-one-voice-short-lines.md](../adr/0017-one-voice-short-lines.md))

## Question

(1) Is Indic-Mio (a 0.6 B language model writing speech tokens, voice taken from the sound alone, no sample text, English
too) a better GPU voice than IndicF5? (2) IndicF5 sometimes swallows short lines: what should speak them?

## Hypothesis

Not recorded; implied: (1) Indic-Mio is faster and needs no sample text; (2) a second voice for lines of 2-4 words
recovers the words IndicF5 loses.

## Setup

- Engines on the A100 GPU VM (address in `docs/v1/NEEDS_APPROVAL.md`): IndicF5 (default) and Indic-Mio
  (`GPU_VOICE_MODEL=mio` + `GPU_MIO_URL`, `gpu_engine/mio_engine.py`); all engines together about 39 of 40 GB.
- Lines alone: one recorded voice, 8 lines a language. Similarity: ECAPA2 (the real person scores 0.86-0.89).
- Live: the dense 24.9 s Hindi reel, six loops, voice learned from the stream, Tamil + Bengali, hold 6 s; Streamer Mode,
  recorded voice, Tamil + Punjabi. One run each. Backend on the laptop, tunnel.
- Short lines: 120 real live phrases spoken twice each by IndicF5 (216 tries), heard back by Prisma. Guard
  (`providers/tts_gpu_guard.py`, `gpu_voice_guard`, `gpu_voice_short_words` = 4).

## Metrics

- Engine time per line, **words heard back** ([GLOSSARY](../GLOSSARY.md)), speaker similarity, ms a word.
- Live: **first audio** p50, **on time** within 1 s, phrases at the 1.3x limit.

## Results

Lines alone, **measured**, 2026-11-21, 8 lines a language, IndicF5 vs Indic-Mio (SPEC.md section 21):

| Metric | IndicF5 | Indic-Mio |
|---|---|---|
| Engine time | 605-612 ms | 274-378 ms |
| Words heard back, Tamil / Punjabi / Bengali | 85 / 91 / 93% | 81 / 88 / 95% |
| Similarity to the speaker | 0.54-0.63 | 0.45-0.57 |
| English | not spoken | 96% words, similarity 0.32 |
| Tamil pace | 657 ms a word | 406 ms a word |

A 3 s sample instead of 9 s gave about the same Indic-Mio similarity (0.47-0.52). Codec speed-up at 1.0 / 1.25 / 1.5 /
1.75x: Tamil words 79 / 80 / 70 / 58%, similarity 0.47 / 0.40 / 0.31 / 0.27.

Live, **measured**, one run each, IndicF5 -> Indic-Mio:

| Run | First audio p50 | Words heard back | Within 1 s | At 1.3x limit |
|---|---|---|---|---|
| Voice from the stream, Tamil + Bengali | 2.6 s -> 2.1 s | 79 / 75% -> 80 / 79% | 87% -> 50% (Bengali 97% -> 27%) | 37 -> 111 of about 155 |
| Streamer, recorded voice, Tamil + Punjabi | 2.8 s -> 2.2 s | Tamil 77 -> 82%, Punjabi 80 -> 75% | 54% -> 60% | not given |

Short lines, **measured**:

- 24 of 216 IndicF5 tries were bad (under half the words); bad ones are short lines. In Bengali 12 of 13 tries under 0.6x
  usual length per letter were lost. The same line made again was good in 1 of 11 cases.

| Lines of 2-4 words | IndicF5 | IndicF5 at 0.75 speed | Indic-Mio |
|---|---|---|---|
| Tamil | 71% | 78% | 85% |
| Bengali | 33% | 67% | 81% |

Lines of 6 and more words: 83-84% on IndicF5.

- Guard off -> on (Indic-Mio for short lines), whole session, one run each: Tamil 78 -> 80%, Bengali 70 -> 74%; within
  1 s 94% -> 94%; first audio p50 2.4 s both. Inside the run-to-run spread.
- **Correction from a real stream the same night:** a third of the founder's stream lines were short and the viewer
  heard a second voice between the copied one. Re-spoken stream lines: IndicF5 0.67 similarity to the sample,
  Indic-Mio 0.39. After moving short lines back to IndicF5 (up to 3 words at 0.75 speed, swallowed line made again
  slower), 40 lines of that stream: short lines 83% heard back (1 of 8 lost), others 87%, one voice throughout.
- That stream alone afterwards: Punjabi 92% within 0.25 s, 99% within 1 s, first audio p50 2.3 s, 73 of 73 lines in the
  copied voice. A test run beside it on the same GPU and tunnel had dropped it to 3.2 s and 56% within 1 s.
- A glossary hint to the speech-to-text model: 15 -> 16 of 22 game words and names right on 10 lines; not added.

## Caveats

- One run per Live arm; two equal runs differ by about 10 points in timing (EXP-013).
- Which voice sounds better was not judged by ear.
- The guard A/B ran on a reel with few short lines; not measured on a stream with many.

## Decision taken

IndicF5 stays the GPU voice; Indic-Mio is a switch. Short lines stay on IndicF5 (`gpu_voice_short_engine` = f5);
`mio` restores the second voice (ADR-0017). One GPU through this tunnel is one stream.

## Links

- [SPEC.md](../../../SPEC.md) section 21 ("A second voice tried in the GPU engine: Indic-Mio"; "Lines the voice engine
  swallows"; "Correction the same night")
- Commits: `59fbbec` (Indic-Mio engine), `4f3d177` (switch and measurements), `b151c39` (guard), `94c8e90` (short
  lines stay on IndicF5)
- Related: [EXP-012](EXP-012-clone-similarity.md), [EXP-016](EXP-016-real-stream-67min.md)
