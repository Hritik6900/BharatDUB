# ADR-0016: In the GPU engine hosted Prisma hears first (73 vs 49 of 80 key words on hard audio); switch `gpu_stt_first` kept

- **Status:** accepted
- **Date:** 2026-11-21
- **Superseded by:** —

## Context

The 67-minute real stream in all-GPU mode (a quiz class, 21 Nov) showed subject words misheard by our Whisper,
then carried into the dub by the translation (`../../../SPEC.md` section 21). The user found the hosted output
better and asked what the GPU engine lacks. A test set was made: 24 class and stream lines with 80 key words,
spoken by two hosted stock voices, clean and "hard" (15% faster, room echo, noise 10 dB under the voice).
It is made speech, not a real teacher.

## Options considered

Key words right out of 80, clean / hard (**measured** 21 Nov, SPEC section 21):

| Option | Result | Outcome |
|---|---|---|
| Our Whisper-Hindi2Hinglish-Apex first | 70 / 49 (Prisma comparison set); 69 / 48 (model comparison set) | kept behind the hosted one |
| Whisper large-v3-turbo | 67 / 40 | rejected |
| Whisper large-v3 | 65 / 50, 388 ms decode against 87 ms | rejected |
| Hold back the last agreed word, beam 5 (`be7540b`) | hard set streamed live: settled key words 41 -> 46 of 80 (whole-utterance decodes had 49) | kept in the engine |
| Utterance before as context | stream finals 49 -> 45 | rejected |
| Hosted Prisma first, our model behind it | 77 / 73 | **chosen** |

Caveat: the test voices are the hosted vendor's own stock voices, which may favour Prisma; the gap on hard audio
is far larger than that could explain (SPEC section 21).

## Decision

`gpu_stt_first` = `hosted` (default): in the GPU engine Prisma hears first with our model behind it
(`FallbackSTT`). `gpu` keeps nothing hosted in the path, as before.

## Consequences

### Good

- The right words reach translation on hard audio. v1 eval repeated it on 23 Nov: hosted 77 of 80 clean,
  71.3 hard (71-72, three runs); our Whisper 70 and 52 (50-55) (`../../v1/PROGRESS.md` phase 8).

### Bad

- Timing cost on the clean dense reel, Tamil + Punjabi, one run each, our model -> Prisma: within 1 s 95% -> 72%,
  within 2 s 99% -> 88%, phrases at the 1.3x limit 43 -> 70 of about 150; first audio p50 2.5 s -> 2.3 s; words
  heard back unchanged (81 / 78% -> 80 / 77%) (**measured** 21 Nov, SPEC section 21). Prisma's partials give
  longer phrases (8 source words against 7).
- The hosted one-request limit and the hosted outage risk (INC-02) are back in the GPU engine's path.
- Not measured: a whole session on hard audio, where the gain should show.
- v1 target "hard-audio key words >= 73/80" is not met by either (hosted 71.3, `../../v1/SUMMARY.md` section 2).

## Evidence

- Experiments: [EXP-018](../experiments/EXP-018-prisma-vs-whisper-hard-audio.md), [EXP-016](../experiments/EXP-016-real-stream-67min.md)
- Commits: `be7540b` (hold-back, beam 5), `3a20c06` (hosted hears first)
- Sources: [`SPEC.md`](../../../SPEC.md) section 21; [`EVAL_REPORT.md`](../../v1/EVAL_REPORT.md) section 3;
  [`PROGRESS.md`](../../v1/PROGRESS.md) phase 8
