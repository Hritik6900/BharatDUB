# EXP-011: Sync stamp fix and hold 6/7.5/9 s

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** ADR-0009 ([../adr/0009-sync-mode-hold.md](../adr/0009-sync-mode-hold.md))

## Question

Why did "on time" sit at 45-70% in sync mode, and does a longer hold or a corrected phrase moment fix it?

## Hypothesis

Not recorded at the start; implied first: the hold is too short. After analysis the hypothesis became: the phrase
moment (stamp) itself is wrong.

## Setup

- Data: the dense 24.9 s Hindi reel, sync mode, voice learned from the stream, Tamil + Bengali; one user session in
  Punjabi for the baseline. Backend on the laptop, GPU voice through the tunnel.
- Step 1, `live_stamp_fix`: a tail starts when its first word showed up in a partial (`Phraser.tail_start`); no phrase
  starts before the one before it ended. First checked by replay of a recorded run (estimate), then live.
- Step 2, same switch: phrases inside one line share the time since the line began at an even pace
  (`Phraser._span`).
- Live A/B: six loops each (about 70 spoken phrases a language), fix off on a second server and fix on, back to back.
- Hold test: stamp fix on, hold fixed, growth off, six loops each, holds 6 / 7.5 / 9 s (about 140 phrases over Tamil +
  Bengali per hold).

## Metrics

- **On time** ([GLOSSARY](../GLOSSARY.md)): dub starts within 0.25 s of the video moment its phrase was spoken at;
  also within 0.5 / 1 / 2 s; p90 lateness; worst.
- **Hold** and skipped phrases.

## Results

Baseline, **measured**, 2026-11-21, one run each (SPEC.md section 20):

| Run | Within 0.25 s | Within 1 s | Within 2 s |
|---|---|---|---|
| Dense reel, Tamil | 45% | 71% | 87% |
| User session, Punjabi | 56% | 81% | 94% |

Of 17 late Tamil phrases, 4 had audio that arrived late and 13 waited for the dub before them. 10 of 36 phrases were
stamped as starting before the previous phrase ended (by up to 1.3 s). **measured**.

Replay with corrected stamps (**estimate**; speed-up decisions would differ in a real run):

| Language | Within 0.25 s | Within 1 s | p90 |
|---|---|---|---|
| Tamil | 45% -> 61% | 71% -> 81% | 2.1 s -> 1.2 s |
| Bengali | 48% -> 67% | 70% -> 82% | not given |

A replay with a 7 s hold instead of 6 s left Tamil at 45% (**estimate**).

Live A/B, fix off -> on, **measured**, one run each way, while the hold was still 6 s (first 70 s, 27-28 phrases a
language):

| Language | Within 0.25 s | Within 0.5 s | Within 1 s | p90 |
|---|---|---|---|---|
| Tamil | 41% -> 46% | 52% -> 68% | 59% -> 79% | 2.1 s -> 1.3 s |
| Bengali | 67% -> 71% | 70% -> 79% | 81% -> 86% | 1.5 s -> 1.4 s |

Whole run: Tamil 49% -> 54% (within 1 s 66% -> 86%), Bengali 59% -> 81% (78% -> 94%); skipped 5 -> 2. In both runs
the hold grew part-way (off: 6 -> 8 s at 100 s; on: 6 -> 9 s at 76 s, in one 3 s step).

Hold test, **measured**, one run per hold, about 140 phrases each:

| Hold | Within 0.25 s | Within 1 s | Within 2 s | Worst |
|---|---|---|---|---|
| 6 s | 64% | 91% | 96% | 3.2 s |
| 7.5 s | 71% | 90% | 100% | 1.9 s |
| 9 s | 62% | 90% | 99% | 2.0 s |

Bengali sat at 78-80% within 0.25 s at every hold, Tamil at 46-61%; 22-30 of about 70 Tamil phrases were at the 1.3x
limit.

## Caveats

- A first "correction" note in SPEC said the hold matters more than the replay showed; the fixed-hold test then showed
  the hold does not move the bulk, only the rare worst cases. Both notes are in SPEC section 20 as written.
- One run per arm; two equal runs differ by about 10 points in timing (SPEC section 20, pace entry).
- What is left in Tamil is dub length, not stamping.

## Decision taken

`live_stamp_fix` on. Hold starts at 6 s; `live_sync_grow_step_ms` = 1000 (growth at most 1 s a step, 3 s before), and a
phrase late in several languages counts once (ADR-0009).

## Links

- [SPEC.md](../../../SPEC.md) section 20 ("Why 'on time' sat at 45-70% in sync mode")
- Commits: `a60b6d8` (stamp fix, replay estimate), `6667f1a` (even pace inside a line, live A/B), `86188e5` (grow
  step 1 s, hold test)
- Related: [EXP-006](EXP-006-sync-mode.md), [EXP-013](EXP-013-steps-and-pace.md)
