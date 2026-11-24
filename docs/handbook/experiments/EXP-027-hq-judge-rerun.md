# EXP-027: Studio HQ with corrected judge, rerun, adaptive takes, text flags (WS3)

- **Date:** 2026-11-25
- **Status:** done
- **Decision:** ADR-0030 ([../adr/0030-hq-judge-and-review.md](../adr/0030-hq-judge-and-review.md))

## Question

Studio HQ read 92.5% words heard back on 23 Nov (EXP-021) against a 96% target. Is the judge right? Can adaptive
takes, a normaliser, an auto-glossary and a rubric review get HQ to 96%? What do adaptive takes save against a fixed
number of takes?

## Hypothesis

More takes and a reviewed translation raise HQ to 96%; adaptive takes save voice time without losing score.

## Setup

- Before building, the kept takes under 90% of the seven 23 Nov HQ jobs (269 stored takes, all scored by the hosted
  speech-to-text) were read: what the dub should say against what the judge heard.
- Three videos of twelve spoken lines (`class12`, `class12b`, `class12c`; 24, 26 and 26 dubbed lines), Tamil +
  Bengali, GPU engine, voice copied from the video with consent, as on 23 Nov.
- **One job per video and setup**, 25 Nov 2026 01:48-02:45 IST, one job at a time, no stream live.
- Setups: standard (all flags off); HQ (`V1_STUDIO_HQ`, `V1_FIT_115`, `V1_ROUTER` + `V1_HQ_JUDGE`); fixed 5 (HQ +
  `V1_HQ_TAKES_FIXED=5`); adaptive (HQ + `V1_HQ_ADAPTIVE` with the same-words stop); all flags (adaptive +
  `V1_HQ_NORMALISE`, `V1_HQ_AUTO_GLOSSARY`, `V1_HQ_REVIEW`). Fixed 5 and adaptive reused the HQ job's transcript
  and translation from its cache.
- Every finished line heard back by the hosted speech-to-text and counted by the corrected rule (380 lines of 15
  jobs, all by that judge). The 23 Nov output scored again from the stored hearings (`eval.v1.rescore`, no new
  voice lines; 1 of 152 finished lines heard again).

## Metrics

Words heard back (mean of the three videos), per video and language, total and voice-stage time, takes, lines
flagged, transcript lines that are no longer the line first heard.

## Results

All **measured**. Source: [EVAL_REPORT.md section 6](../../v1/EVAL_REPORT.md),
[PROGRESS.md "v1.1 WS3"](../../v1/PROGRESS.md).

**Found first, the judge's counting rule.** One Bengali letter can be stored two ways (one code point, or base
letter plus a dot below). The translation model writes one form, the speech-to-text the other, and v1 counted them
as different words: a Bengali line heard back word for word scored 86%. Devanagari has the same two forms; Tamil
does not. The rule now normalises both texts (Unicode NFC, rule "nfc-2").

| | 23 Nov, as reported (old rule) | 23 Nov output, new rule | 25 Nov rerun, new rule |
|---|---|---|---|
| Standard, words heard back | 89.2% (84.9-93.4) | 91.1% (87.3-95.3) | 90.6% (88.4-93.0) |
| HQ, words heard back | 92.5% (91.1-93.5) | 95.5% (93.9-96.7) | 95.9% (93.3-98.1) |
| HQ lines flagged, of 76 | 25 | 15 | 15 |
| HQ takes | 179 | 179 | 143 |
| HQ time a video, mean | 255 s | same jobs | 128 s (133 / 117 / 136) |
| Standard time a video | 84 / 78 / 84 s | same jobs | 81 / 54 / 66 s |

The new rule moved Bengali by 5.6-6.3 points on HQ and 2.7-4.6 on standard; Tamil by nothing. **HQ did not get
better between 23 and 25 Nov: it had been at 95.5% all along and was reported as 92.5%.**

**Found second, transcript damage.** Heard-back compares the dub with its own text. v1's "merge the hearings" and
"clean" steps had changed the transcript: video C, 12 of 13 lines hold the line before them; video B, all 13 lines
in Latin letters and three without their first words; video A unchanged. Those jobs scored 93.3% and 98.1%. In
the HQ jobs 25 of 38 lines of videos B and C are not the line heard; with `V1_HQ_REVIEW` (transcript guard) 0.
See [INC-07](../INCIDENTS.md#inc-07-hq-transcript-damage-found).

Rerun, mean (lowest-highest video), one job per video:

| | Standard | HQ | Fixed 5 | Adaptive | All flags |
|---|---|---|---|---|---|
| Words heard back | 90.6% (88.4-93.0) | **95.9%** (93.3-98.1) | 96.1% (92.3-99.1) | 95.0% (93.2-97.8) | **94.5%** (93.2-96.5) |
| Total time A / B / C | 81 / 54 / 66 s | 133 / 117 / 136 s | 193 / 195 / 199 s | 86 / 86 / 101 s | 140 / 129 / 130 s |
| Takes A / B / C | 24 / 26 / 26 | 45 / 45 / 53 | 120 / 130 / 130 | 43 / 45 / 55 | 53 / 52 / 51 |
| Lines flagged, of 76 | not scored | 15 | 11 | 18 | 21 |
| Transcript lines not the line heard A / B / C | does not merge | 0 / 13 / 12 | 0 / 13 / 12 | 0 / 13 / 12 | 0 / 0 / 0 |

- **Adaptive against fixed 5:** voice stage 524 s -> 206 s over the three videos (61% less), 380 -> 143 takes.
  The clean comparison (the adaptive rule applied to the fixed jobs' own 380 takes): best of five 96.8%; adaptive
  keeps the same take on all 76 lines (96.8%) with 145 takes; first take alone 93.8%. With the same-words stop:
  129 takes, 96.3%, a lower take kept on 3 lines (stop now off by default). Against v1's own earlier rule (up to
  four takes until one passes) adaptive saves nothing: both 143 takes.
- **Review:** 76 lines read, 24 edits, all taken (12 numbers and names, 9 meaning, 2 register, 1 length), 77 model
  calls in three jobs (HQ without: 42). A first build: 94.8% (93.0-95.8), 30 edits, 2 refused; one refused edit was
  a meaning error left in the dub, which led to the "ask again" step.
- **Auto-glossary:** 16 candidates over three videos; effect not separated from the review's.
- **Normaliser:** changed no line (the videos say numbers as words); unit tests only.
- All-flags jobs score lower than HQ (94.5% vs 95.9%); read line by line, most flags are spellings the judge writes
  differently for the same sound and English terms in the other script.
- Calibration page (`/studio/calibrate`): **no labels yet**, so no agreement figure and no recommended flag line.

Target 96%: **not reached.** HQ 95.9% (two of three videos over 96%, two of three dubbing a damaged transcript); all
flags, with intact transcripts, 94.5% (one of three over 96%).

## Caveats

- One job per video and setup; two equal jobs differ widely (standard Tamil on video A: 93.9% on 23 Nov, 82.9% on
  25 Nov).
- "Words heard back" is not a listener: it marks spelling variants as misses and a wrong sentence as heard. Nobody
  has listened; the 90% flag line and the 96% target are not tied to a person's ear.
- Tamil and Bengali only; Hindi as a target not measured (its second judge tested with fakes only). Speaker
  similarity not measured. No digits in the videos, no music, no long video.
- Mistake during the work: the first fixed-5 and adaptive jobs were spoken by the hosted copy (a copied cache named a
  sample file the other backend could not open); they were set aside and rerun on fresh backends (150 hosted lines
  spent). Five comparison backends were left running on 8111-8115.
- Hosted and GPU use: 152 clips transcribed (437 s of audio), 1137 takes and 480 finished lines heard back, 1224
  voice lines (150 by the hosted copy), 187 model calls, 18 voice copies made.

## Decision taken

`V1_HQ_JUDGE` and `V1_HQ_REVIEW` on whenever HQ is on; HQ is not offered without the review (ADR-0030).
`V1_HQ_ADAPTIVE`: on per V1_1_SUMMARY section 3, off per the v1 runbook and summary (it saves time only against five fixed takes; against v1's own rule both make 143 takes); open, see [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md). `V1_HQ_NORMALISE` and `V1_HQ_AUTO_GLOSSARY` off. Thirty labels a language on the calibration
page before the target or the flag line are trusted.

## Links

- [docs/v1/EVAL_REPORT.md](../../v1/EVAL_REPORT.md), section 6
- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "v1.1 WS3"
- [docs/v1/CALIBRATION.md](../../v1/CALIBRATION.md)
- `logs/jobs/index.csv` rows `ws3-*`, `logs/trace/ws3-*/`
- Commit: `93b5e75`
- Related: [EXP-021](EXP-021-studio-hq-vs-standard.md), [ADR-0024](../adr/0024-studio-hq-takes.md),
  [ADR-0030](../adr/0030-hq-judge-and-review.md)
