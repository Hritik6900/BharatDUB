# EXP-032: Studio HQ in auto mode on the three test videos

- **Date:** 2026-11-26
- **Status:** done (one job per video)
- **Decision:** ADR-0036 ([../adr/0036-auto-mode.md](../adr/0036-auto-mode.md))

## Question

In auto mode a Studio HQ job runs with everything on that v1.1 kept behind flags (review, judge, adaptive takes,
normaliser, a job's own glossary, the 1.15x fit limit) and with the two new guards (script, content shift) and the
fallback to another voice. Is its output as good as the best v1.1 setting, what does it cost in time, and what do
the guards find?

## Hypothesis

None was written down before the jobs. What the build expected (ADR-0036 as drafted): the output of v1.1's
"HQ + all flags" (94.5%), with a model call more per language for the content-shift guard.

## Setup

- Material: the three 50 s test videos of [EXP-021](EXP-021-studio-hq-vs-standard.md) and
  [EXP-027](EXP-027-hq-judge-rerun.md) (A, B, C: 12, 13 and 13 lines; speech made by hosted stock voices, no music),
  Tamil + Bengali, 76 dubbed lines in all.
- One comparison backend on the laptop, port 8120, `scripts\v1\ab-server.ps1 -Mode auto`, no overrides, its own
  empty data folder (nothing cached). GPU engine, voice copied from the video with consent, `quality=hq`.
- One job per video, one at a time, 2026-11-26 14:46-14:54 UTC, nobody live on v0 or v1, no other session or job
  on the GPU. Driven by `scripts/v1/eval-studio-ws3.sh` (`SETUPS="auto:8120:hq"`), tables by
  `python -m eval.v1.studio_table <out> --ab data-v1/ab --names auto=p3-auto`.
- Every finished line was heard back by the hosted speech-to-text and counted by the corrected rule (`nfc-2`), as
  in EXP-027.
- **The v1.1 rows below are EXP-027's jobs of 25 Nov 2026: another day, not interleaved with these.** Two equal
  jobs have differed by more than most of the differences here (EXP-027: the standard pipeline's Tamil on video A
  93.9% and 82.9%).

## Metrics

- **Words heard back:** share of a dubbed line's words the hosted speech-to-text returns ([GLOSSARY](../GLOSSARY.md)).
  It compares the dub with its own text; it cannot see a wrong transcript or a wrong translation.
- **Script guard:** every translated line; "wrong" = letters of another script, "flagged" = still wrong after one
  new translation. It sees letters, not words.
- **Content shift:** every translated line judged beside its source by a language model before the voice; "wrong" =
  judged as saying something different or as missing something that matters, "flagged" = still so after one new
  translation; "not checked" = the judge gave no answer for the line.
- **Damaged transcript:** lines whose cleaned transcript is no longer the line first heard (EXP-027's check).

## Results

All **measured**, one job per video.

| | Standard, v1.1 (25 Nov) | HQ, v1.1 (25 Nov) | HQ + all flags, v1.1 (25 Nov) | **HQ, auto mode (26 Nov)** |
|---|---|---|---|---|
| Words heard back, mean of 3 videos (lowest-highest) | 90.6% (88.4-93.0) | 95.9% (93.3-98.1) | 94.5% (93.2-96.5) | **95.6% (94.6-96.5)** |
| ... video A / B / C | 88.4 / 90.4 / 93.0 | 96.2 / 98.1 / 93.3 | 93.2 / 93.9 / 96.5 | 96.5 / 94.6 / 95.5 |
| ... Tamil, A / B / C | 82.9 / 95.5 / 90.7 | 96.6 / 97.8 / 87.5 | 90.7 / 94.3 / 96.2 | 95.8 / 93.8 / 95.0 |
| ... Bengali, A / B / C | 94.0 / 85.4 / 95.2 | 95.9 / 98.4 / 99.2 | 95.7 / 93.5 / 96.8 | 97.2 / 95.5 / 96.1 |
| Total time, A / B / C | 81 / 54 / 66 s | 133 / 117 / 136 s | 140 / 129 / 130 s | **146 / 152 / 160 s** |
| Voice stage, A / B / C | 23 / 24 / 25 s | 73 / 67 / 79 s | 77 / 73 / 75 s | 74 / 93 / 92 s |
| Translate stage (with the review; in auto also the two guards), A / B / C | 11 / 5 / 10 s | 13 / 13 / 16 s | 19 / 22 / 19 s | 26 / 24 / 29 s |
| Takes made, of 76 lines | 76 | 143 | 156 | 178 |
| Lines flagged, of 76 | does not score | 15 | 21 | 20 |
| Damaged transcript lines, A / B / C | does not merge | 0 / 13 / 12 | 0 / 0 / 0 | 0 / 0 / 0 |

The video rows of the v1.1 columns are the means of the two languages in `docs/v1/EVAL_REPORT.md` section 6.2.

Guards in the three auto jobs (each its own count; 76 lines):

| Guard | Checked | Failed | Translated again and passed | Flagged | Not checked |
|---|---|---|---|---|---|
| Script (every line) | 76 | 0 | 0 | 0 | 0 |
| Content shift (every line, judged by the hosted model) | 76 | 0 | 0 | 0 | 0 |
| Shortened to fit, judged once more | 0 lines were shortened | - | - | 0 | - |
| No voice could say the line (unspoken) | - | 0 | - | 0 | - |

- **Flagged lines: 20 of 76** (A 4, B 9, C 7; Tamil 12, Bengali 8). Every one is flagged by the heard-back judge,
  none by a guard: after the five takes the adaptive rule allows, the best take had 67-89% of its words heard back
  (under the 90% line). 12 of the 20 are at 86-89%.
- **Review:** 21 of 76 lines edited (numbers and names 11, meaning 7, length 2, register 1), all taken.
- **Transcript:** one line of video B was changed by the clean step and is still the line that was heard; none is
  damaged.
- No job had a warning; no line was spoken by another voice than the copied one.

Reading it:

- Words heard back is in the range of the v1.1 HQ settings (95.6% against 95.9% with two damaged transcripts and
  94.5% with intact ones). One job per video, another day: no difference is shown. **The 96% target is not
  reached** (one video of three over 96%).
- **Auto is slower than both v1.1 HQ settings in all three videos:** 152 s a video at the mean against 129 s (HQ)
  and 133 s (HQ + all flags). Of the 19 s over "all flags", about 6 s a video is the translate stage (every line is
  judged once more before the voice: 26 s against 20 s at the mean) and about 11 s is the voice stage, which made
  more takes (178 against 156). Why more takes: 20 lines went to the limit of five takes without reaching 90%;
  with one job per video this cannot be told from chance.
- **The content-shift guard found nothing, and that is weak evidence that nothing is wrong.** The judge is the
  hosted model, the same model that had just reviewed and edited these lines against the same rubric; a second
  look by the same eyes. The script guard found nothing on text that has no mixed script.
- So: the output is where v1.1's HQ settings were, with intact transcripts, for about 19 s more a video.

## Caveats

- One job per video and setup; the v1.1 columns are from another day.
- Clean test videos: speech made by stock voices, no music, no numbers written as digits, one speaker. The guards
  were not seen to catch anything, so what they do to a line that fails (translate again, flag) ran only in tests.
- Nobody listened to a line; the 20 flagged lines were not read by a speaker of Tamil or Bengali.
- The fallback to another voice did not happen in any job: tested with fake providers only.
- A standard job in auto mode was not measured (the task asked for HQ).

## Decision taken

None changed. Auto mode keeps HQ as built; the numbers go into ADR-0036.

## Links

- [EXP-027](EXP-027-hq-judge-rerun.md) (the v1.1 columns), [EXP-021](EXP-021-studio-hq-vs-standard.md)
- [EXP-031](EXP-031-auto-mode-dense-reel.md) (auto mode in Live)
- Code: `backend/app/v1/lineguard.py`, `backend/app/v1/guards.py`, `backend/app/v1/hq/`; harness
  `backend/eval/v1/studio.py`, `studio_table.py`, `scripts/v1/eval-studio-ws3.sh`
- Run data: `data-v1/eval/v12/studio/` and `data-v1/ab/p3-auto/` on the build laptop (not in git);
  `logs/jobs/index.csv` rows `p3-auto`
