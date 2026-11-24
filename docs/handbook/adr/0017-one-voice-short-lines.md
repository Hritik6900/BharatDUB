# ADR-0017: Short lines stay in IndicF5 (slower), Indic-Mio second voice rejected as default

- **Status:** accepted
- **Date:** 2026-11-21
- **Superseded by:** —

## Context

IndicF5 sizes a line by its length; a line of 2-4 words often gets no time and comes out empty. 120 real live
phrases spoken twice each and heard back by Prisma: 24 of 216 tries bad (under half the words), mostly short
lines; the same line made again was good in 1 of 11 cases, so a plain retry does not help (**measured** 21 Nov,
`../../../SPEC.md` section 21). A second engine was tried the same night: Indic-Mio (0.6 B language model + codec,
no sample text needed, English too).

## Options considered

Lines of 2-4 words, words heard back, IndicF5 / IndicF5 at speed 0.75 / Indic-Mio: Tamil 71 / 78 / 85%, Bengali
33 / 67 / 81% (**measured** 21 Nov, SPEC section 21).

| Option | Measured | Outcome |
|---|---|---|
| Indic-Mio as the GPU voice for everything (`GPU_VOICE_MODEL=mio`) | Live: first audio p50 2.6 -> 2.1 s, but within 1 s 87% -> 50% (Bengali 97% -> 27%); speaks at its own pace | switch only, default stays IndicF5 (`4f3d177`) |
| Indic-Mio for lines of up to 4 words, swallowed lines remade there | whole session: words Tamil 78 -> 80%, Bengali 70 -> 74%, within the run-to-run spread (`b151c39`) | **reversed** the same night |
| IndicF5 for every line; up to 3 words at 0.75 speed; a swallowed line remade slower | short lines 83% heard back (1 of 8 lost), others 87%, one voice throughout (40 lines of the real stream) | **chosen** (`94c8e90`) |

Why the second voice was reversed: on the user's real stream (a quiz class, Punjabi) a third of the lines were
short, and the viewer heard a second voice between the copied ones. The stream's own lines spoken again: IndicF5
lines 0.67 close to the sample, Indic-Mio lines 0.39 (SPEC section 21).

## Decision

`gpu_voice_short_engine` = `f5`: every line stays on IndicF5. `gpu_voice_guard` and `gpu_voice_short_words`
remain; `mio` restores the second voice for short lines.

## Consequences

### Good

- One voice through a session. After the change the real stream (alone) measured Punjabi 92% within 0.25 s,
  99% within 1 s, first audio p50 2.3 s, 73 of 73 lines in the copied voice (SPEC section 21).

### Bad

- Short lines are slow (0.75 speed) and often longer than their slot: 65 of 108 over-long Tamil lines in v1's
  dense runs were 1-3 word lines (`../../v1/LIVE_DENSE_REPORT.md` section 5).
- One-word lines can still be lost ("Bolo.", 1 of 8).
- Which of the two engines sounds better was not judged by ear.

## Evidence

- Experiments: [EXP-017](../experiments/EXP-017-indic-mio-vs-indicf5.md), [EXP-016](../experiments/EXP-016-real-stream-67min.md)
- Commits: `59fbbec`, `4f3d177` (Indic-Mio behind a switch), `b151c39` (second voice for short lines), `94c8e90` (one voice)
- Sources: [`SPEC.md`](../../../SPEC.md) section 21; [`LIVE_DENSE_REPORT.md`](../../v1/LIVE_DENSE_REPORT.md) section 5
