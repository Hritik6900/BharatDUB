# ADR-0028: Live timing is a dub-duration problem, not latency: duration budget + rate control

- **Status:** accepted (budget: on for Punjabi-like; controller off)
- **Date:** 2026-11-24
- **Superseded by:** —

## Context

On real videos of 24 Nov (Punjabi) the share of phrases whose dub starts within 0.25 s of its video moment fell
from 95% to 76% when the speaker talked 76% of the time instead of 62%; the 1.3x speed limit was hit on 16-40% of
lines; a longer hold had not helped before (`../../v1/LIVE_DENSE_REPORT.md` intro; ADR-0009). The dubbed line is
longer than the time the speaker took, so every line starts later than the one before. v0 already gave the
translator a word limit from the speaker's average pace (`live_length_budget`, `live_brief`, 14 Nov) but checked
nothing (`../../v1/LIVE_DENSE_REPORT.md` section 2). The v1 phase 5 flags had moved neither first audio nor on-time
(ADR-0029, EXP-020).

## Options considered

Dense 24.9 s reel played 8 times (211 s, 89% speaking, 5.1 words/s), GPU engine, Punjabi + Tamil, learned voice,
sync mode, hold 6 s, **5 runs each**, mean (lowest-highest) (**measured** 24 Nov, `../../v1/LIVE_DENSE_REPORT.md` section 1):

| | Flags off | Budget (`V1_LIVE_BUDGET`) | + controller (`V1_LIVE_RATECTRL`) | + engine speed (`V1_LIVE_NATIVE_SPEED`) |
|---|---|---|---|---|
| Within 0.25 s | 63.5% (57.9-68.6) | 80.6% (77.8-83.6) | 83.1% (81.9-84.4) | 82.8% (80.5-85.9) |
| Within 1 s (target 90%) | 86.5% (84.2-90.6) | 92.3% (89.8-96.1) | 91.8% (89.2-95.3) | 91.5% (87.7-94.7) |
| Dub length / slot p90 (target 1.0) | 1.42 | 1.17 | 1.11 | 1.09 |
| Skips per 10 min (target 1) | 7.1 (0-17.9) | 7.8 (0-35.8) | 9.5 (0-32.7) | 19.7 (0-44.8) |
| First audio p50 / p95 | 2.41 / 3.92 s | 2.63 / 4.40 s | 2.65 / 4.69 s | 2.62 / 4.75 s |

Also tried: no tolerance (`V1_BUDGET_OVER=1.0`, 3 runs each): p90 1.07 against 1.10, every line shorter, no gain;
default stays 1.15.

## Decision

- `V1_LIVE_BUDGET`: the translator gets the phrase's own slot as words and letters from a per-language expansion
  model (ms of dub per letter / word / source word), a compact register, "keep names and numbers"; an answer more
  than 15% over gets one shorter re-ask (2.5 s at most). Recommended **on** for Punjabi-like languages; **the
  user's call for Tamil**.
- `V1_LIVE_RATECTRL` (PI controller on the backlog, dense mode up to 1.4x): **off** until someone has heard 1.4x.
- `V1_LIVE_NATIVE_SPEED`: **off**, no number moved.
- New per-phrase measures `dur_ratio` and `backlog` stay on with the trace.

## Consequences

### Good

- Within 1 s reached 90% (7 of 10 runs at 90% or more). Phrases late because they queued behind a long dub: 8.9% ->
  2-3% (`../../v1/LIVE_DENSE_REPORT.md` section 5).

### Bad

- 15-18% fewer letters said; about half the lines asked twice (translation p50 537 -> 714 ms). Words heard back
  Punjabi 87.7% -> 80.1%, Tamil 84.4% -> 82.9% (40 lines a cell). Of 20 lines read per language (not by a native
  speaker) 2 Punjabi and 7 Tamil lost something that mattered.
- One switch for every language: it cannot be on for Punjabi and off for Tamil.
- Skips not reduced: they come in bursts behind stalls (ADR-0027 acts on those).
- Not measured: a real long recording (none exists, item 20), stock voices, the hosted engine, how 1.4x sounds.

## Evidence

- Experiments: [EXP-024](../experiments/EXP-024-dense-speech-budget.md), [EXP-020](../experiments/EXP-020-v1-live-flags.md)
- Commits: `5ec5f4c` (step 1: `dur_ratio`, backlog, expansion model), `ce156a8` (step 2: measured)
- Sources: [`LIVE_DENSE_REPORT.md`](../../v1/LIVE_DENSE_REPORT.md) sections 1, 2, 5, 6, 8;
  [`PROGRESS.md`](../../v1/PROGRESS.md) v1.1 WS1; [`SPEC.md`](../../../SPEC.md) section 16 (`live_length_budget`)
