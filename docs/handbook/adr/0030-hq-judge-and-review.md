# ADR-0030: HQ judge counting rule corrected; HQ only together with review (transcript guard)

- **Status:** accepted
- **Date:** 2026-11-25
- **Superseded by:** —

## Context

Studio HQ (ADR-0024) scored 92.5% words heard back on 23 Nov against a 96% target. Before building more, the
stored takes of the 23 Nov HQ jobs were read line by line (`../../v1/PROGRESS.md` v1.1 WS3):

1. **The judge was wrong, not the voice.** One Bengali letter can be stored two ways (য়, ড়, ঢ় as one code point,
   or a base letter plus a dot). The translation model wrote one form, the speech-to-text the other; v1 counted
   them as different words. A Bengali line heard word for word scored 86%, and every take scored the same.
   Devanagari has the same two forms; Tamil does not.
2. **The HQ transcript steps changed what the video says, and heard-back cannot see it.** Video C: 12 of 13 lines
   held the line before them (the merge step answered with the context line). Video B: all 13 lines came back in
   Latin letters, three without their first words. Video A: no line changed. Heard-back compares the dub with its
   own text, not with what the speaker said. INC-07 in [`../INCIDENTS.md`](../INCIDENTS.md).

## Options considered

| Option | Outcome |
|---|---|
| Change the judge model | not needed: the fault was the counting rule |
| Corrected counting rule + judge order per language (`V1_HQ_JUDGE`) | **chosen** |
| Drop HQ's merge/clean steps | not decided: a decision for the user (`../../v1/SUMMARY.md` section 4, decision 6) |
| Reviewed translation with a transcript guard (`V1_HQ_REVIEW`): a cleaned line that is no longer the line heard is put back (`keeps_source`) | **chosen**, required with HQ |

## Decision

`V1_HQ_JUDGE` and `V1_HQ_REVIEW` are on whenever `V1_STUDIO_HQ` is on (`../../v1/SUMMARY.md` section 2;
`../../v1/RUNBOOK.md` section 3). The judge per language is `V1_HQ_JUDGE_ORDER=prisma,whisper_gpu,qa_server`; a
judge that does not hear a language is left out (our Whisper is Hindi-only).

## Consequences

### Good

Three videos, 76 lines, Tamil + Bengali, one job per video and setup (**measured** 25 Nov,
`../../v1/EVAL_REPORT.md` section 6):

| | 23 Nov, old rule | 23 Nov output, new rule | 25 Nov rerun |
|---|---|---|---|
| Standard | 89.2% | 91.1% | 90.6% |
| HQ | 92.5% | 95.5% | 95.9% |
| HQ lines flagged, of 76 | 25 | 15 | 15 |

- Bengali +5.6 to 6.3 points on the same HQ output; Tamil unchanged.
- Damaged transcript lines: 25 of 38 without the review, 0 with it.

### Bad

- With the review on, words heard back are 94.5% against 95.9%: lower, and not because the dub is worse as far as
  the lines read show. Target 96% still not reached.
- The guard is a rule about words, not a proof that a line is right; 24 of 76 lines were edited by the hosted
  reviewer and need ears.
- "96% heard back" is not tied to what a listener hears until lines are labelled on `/studio/calibrate`
  (`../../v1/NEEDS_APPROVAL.md` item 21).

## Evidence

- Experiments: [EXP-027](../experiments/EXP-027-hq-judge-rerun.md), [EXP-021](../experiments/EXP-021-studio-hq-vs-standard.md)
- Commits: `93b5e75` (WS3)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) v1.1 WS3; [`EVAL_REPORT.md`](../../v1/EVAL_REPORT.md) section 6;
  [`V1_1_SUMMARY.md`](../../v1/V1_1_SUMMARY.md) section 2.5
