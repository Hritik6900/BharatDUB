# EXP-021: Studio HQ vs standard (phase 7/8)

- **Date:** 2026-11-23
- **Status:** done
- **Decision:** ADR-0024 ([../adr/0024-studio-hq-takes.md](../adr/0024-studio-hq-takes.md))

## Question

Does Studio HQ (two hearings merged, cleaned transcript, translation with a word limit per line, several voice takes
per line scored by "words heard back", best kept, weak lines flagged) reach the target of 96% of words heard back,
and what does it cost in time against the standard path?

## Hypothesis

Picking the best of several takes raises words heard back above standard's 91-93% (v0's level) to at least 96%,
for roughly two to three times the time.

## Setup

- Videos: three 50 s "class" videos of twelve spoken lines each, made from the hard set's speech by hosted stock
  voices (`eval/v1/make_video.py`): 24, 26 and 26 dubbed lines a job. Also the dense 24.9 s one-line reel.
- GPU engine, Tamil + Bengali, the voice copied from the video with consent.
- Standard = every flag off. HQ = `V1_STUDIO_HQ`, `V1_FIT_115`, `V1_ROUTER`.
- Scorer: every finished line (after fitting) heard back by the hosted speech-to-text, same scorer for both paths
  (`eval/v1/studio.py`, `GET /api/v1/jobs/{id}/backcheck`).
- **One job per video and path** (a second run is served from the cache). Backend on the laptop.

## Metrics

Words heard back (share of a line's words the scorer returns, mean of lines), turnaround with nothing cached,
takes made, lines flagged (kept take under 0.9), largest speed-up.

## Results

All **measured**, 2026-11-23. Source: [EVAL_REPORT.md section 2](../../v1/EVAL_REPORT.md),
[PROGRESS.md "Phase 7" and "Phase 8"](../../v1/PROGRESS.md).

Three videos, as reported on 23 Nov (counting rule of that day, later found wrong for Bengali):

| Video | Standard: heard back | HQ: heard back | Standard: time | HQ: time | HQ takes | HQ flagged |
|---|---|---|---|---|---|---|
| A | 93.4% | 92.9% | 84 s | 222 s | 54 | 8 of 24 |
| B | 84.9% | 93.5% | 78 s | 312 s | 62 | 8 of 26 |
| C | 89.3% | 91.1% | 84 s | 232 s | 63 | 9 of 26 |
| **Mean (range)** | **89.2% (84.9-93.4)** | **92.5% (91.1-93.5)** | 82 s | 255 s | 60 | 25 of 76 |

- Inside HQ, first take against kept take: Tamil 85.0 -> 95.8% (A), 91.2 -> 97.4% (B), 92.4 -> 94.1% (C); Bengali
  87.7 -> 90.1%, 83.4 -> 89.6%, 87.8 -> 92.1%. Picking among takes is where the gain is (2 to 11 points).
- Largest speed-up: standard 1.00 / 1.00 / 1.05x, HQ 1.02 / 1.06 / 1.15x (the 1.15x limit held).
- Dense one-line reel: standard 41 s and 88.2%, HQ 92 s and 87.7%; no speed-up in either.
- Phase 7 alone (video A, the first run of the day) read HQ 92.9% against standard 93.4%: equal. Phase 8, over three
  videos, read HQ 3.3 points ahead.
- **Correction (2026-11-25, EXP-027):** the counting rule treated a Bengali letter stored two ways as two words.
  The same 23 Nov output by the corrected rule: **standard 91.1% (87.3-95.3), HQ 95.5% (93.9-96.7)**; HQ flags
  25 -> 15 of 76.

## Caveats

- One job per video; two equal jobs differ by more than most differences here (EXP-027: standard Tamil on video A
  read 93.9% on 23 Nov and 82.9% on 25 Nov).
- Test speech made by hosted stock voices; no real creator video, no music under the voice, no two speakers.
- "Words heard back" compares the dub with its own text; it cannot see a wrong transcript (EXP-027 found two of
  these three HQ jobs had one).
- One HQ job lost a request to our voice engine; because a job keeps the voice that spoke first, all 13 Bengali
  lines of that job went to the hosted copy of the voice. 13 of the 76 HQ lines above are in the hosted copy.
- Speaker similarity not measured (no QA server; the earlier model is non-commercial, ADR-0025).
- The scorer was corrected once during the run (abbreviations said letter by letter); tables use the corrected rule.

## Decision taken

- HQ ships behind `V1_STUDIO_HQ` as a choice per job (ADR-0024). Target 96% **not reached** on 23 Nov.
- A job's own voice is now tried twice before another voice answers (test added in `8608b97`).
- Re-measured with a corrected judge in EXP-027.

## Links

- [docs/v1/EVAL_REPORT.md](../../v1/EVAL_REPORT.md), section 2 and section 6
- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "Phase 7", "Phase 8"
- Commits: `3654789` (phase 7), `8608b97` (phase 8)
- Related: [EXP-027](EXP-027-hq-judge-rerun.md), [ADR-0024](../adr/0024-studio-hq-takes.md),
  [ADR-0030](../adr/0030-hq-judge-and-review.md)
