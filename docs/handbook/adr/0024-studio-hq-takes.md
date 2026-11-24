# ADR-0024: Studio HQ: several takes per line scored by heard-back (and similarity), best kept, weak lines flagged

- **Status:** accepted (flag)
- **Date:** 2026-11-23
- **Superseded by:** — (the judge's counting rule and the transcript guard were corrected by [ADR-0030](0030-hq-judge-and-review.md))

## Context

Studio's standard path speaks each line once. A copied voice comes out differently each time ("the engine draws a
new random start each time"; worst lines 0-29% heard back, 21 Nov, `../../../SPEC.md` section 20). v1 set a target
of Studio words heard back >= 96% (from 91-93%) and speed-up <= 1.15x (`../../v1/ARCHITECTURE.md`, "Targets").

## Options considered

| Option | Outcome |
|---|---|
| One take per line (standard) | kept as the default path |
| Several takes per line, each heard back, best kept, failing lines flagged (`V1_STUDIO_HQ`) | **chosen**, as a choice per job |
| Fixed 5 takes every line | measured 25 Nov: 524 s of voice time against 206 s adaptive, same take kept on 76 of 76 lines (`../../v1/EVAL_REPORT.md` section 6.3) |
| Speaker similarity as a gate | not yet: `V1_HQ_SIMILARITY_MIN=0` until the new model's scale is measured (ADR-0025) |

## Decision

`V1_STUDIO_HQ` (with `V1_FIT_115`): two hearings merged, cleaned transcript, translation with a word limit per line,
review, numbers as words, takes scored and the best kept, flagged lines, sidechain ducking, loudness. A line passes
at heard-back >= `V1_HQ_BACKCHECK_MIN` (0.9) and speed-up <= 1.15x. A line no scorer could check is reported as
unchecked, not failed. The editor shows every take with its scores and a one-click swap (`../../v1/PROGRESS.md` phase 7).

## Consequences

### Good

- Three videos, Tamil + Bengali (**measured** 23 Nov, one job per video and setup): HQ 92.5% (91.1-93.5) words
  heard back against 89.2% (84.9-93.4) for standard (`../../v1/SUMMARY.md` section 2).
- By the corrected rule (ADR-0030): 95.5% against 91.1% on the same output; rerun 25 Nov 95.9% against 90.6%,
  128 s against 67 s a video.

### Bad

- Time: 255 s against 82 s for a 50 s video on 23 Nov; a third of the lines flagged.
- Target 96% not reached (95.9%).
- Heard-back cannot see a damaged transcript: two of three HQ test videos were dubbed from one (25 of 38 lines)
  until the review guard (ADR-0030).
- Several flagged lines had the same score on every take: the scorer or the wording, not the voice
  (`../../v1/PROGRESS.md` phase 7).

## Evidence

- Experiments: [EXP-021](../experiments/EXP-021-studio-hq-vs-standard.md), [EXP-027](../experiments/EXP-027-hq-judge-rerun.md)
- Commits: `3654789` (phase 7), `8608b97` (eval harness and report), `93b5e75` (WS3)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) phases 7-8; [`EVAL_REPORT.md`](../../v1/EVAL_REPORT.md) sections 2 and 6;
  [`SUMMARY.md`](../../v1/SUMMARY.md) section 2
