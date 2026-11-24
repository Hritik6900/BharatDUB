# EXP-024: Dense speech: budget, controller, native speed (WS1)

- **Date:** 2026-11-24
- **Status:** done
- **Decision:** ADR-0028 ([../adr/0028-dub-duration-budget.md](../adr/0028-dub-duration-budget.md))

## Question

On dense speech the dubbed line is longer than the time the speaker took, so each line starts later than the one
before (EXP-022: within 0.25 s fell from 95% to 76% when the speaker talked 76% of the time instead of 62%). Can a
duration budget for the translator, a rate controller and engine speed bring the dub back to its slot?

Targets: within 1 s at least 90%; `dur_ratio` (dubbed seconds / source slot seconds) p90 at most 1.0; at most 1
phrase skipped per 10 minutes.

## Hypothesis

Live timing on dense speech is a dub-duration problem, not a latency problem. Asking the translator for a line that
fits the phrase's own slot (and once more for a shorter one when it does not) cuts `dur_ratio` and the backlog, and
raises on-time, at some cost in content.

## Setup

- Material: the dense 24.9 s Hindi reel played 8 times with 0.4 s between and 6 s of silence first (211 s a run).
  The speaker talks 89% of the time, 5.1 words a second inside a phrase. A loop of one reel, not a long real
  recording (none exists on the machine).
- GPU engine, Punjabi + Tamil with a viewer on each, voice learned from the stream with consent, sync mode, hold
  fixed at 6 s (`LIVE_SYNC_ADAPT=false`), every other v1 flag off. Backend on the laptop, tunnel to the GPU.
- Four comparison backends (8111-8114), runs in turn: off, `V1_LIVE_BUDGET`, budget + `V1_LIVE_RATECTRL`,
  + `V1_LIVE_NATIVE_SPEED`. **5 runs each**, 20 runs, 0 failed. Harness `backend/eval/live_replay.py`.
- Extra: 3 runs against 3 of the controller with no tolerance (`V1_BUDGET_OVER=1.0`).
- Words heard back: 20 lines a language from runs 3 and 4 of a setting (40 lines a cell), hosted speech-to-text.
  Meaning: 20 consecutive lines a language read against their sources by the author (not a native speaker).

## Metrics

Within 0.25 s / 1 s / 2 s of the moment, `dur_ratio` p50/p90, backlog p95, skips per 10 min, lines at the speed
limit, first audio p50/p95, copied-voice share, translation p50, letters per source word, words heard back.

## Results

All **measured**, 2026-11-24, mean (lowest-highest of 5 runs). Source:
[LIVE_DENSE_REPORT.md sections 1, 4-6](../../v1/LIVE_DENSE_REPORT.md).

| | off | budget | budget + controller | + engine speed |
|---|---|---|---|---|
| Within 0.25 s | 63.5% (57.9-68.6) | 80.6% (77.8-83.6) | 83.1% (81.9-84.4) | 82.8% (80.5-85.9) |
| Within 1 s (target 90%) | 86.5% (84.2-90.6) | 92.3% (89.8-96.1) | 91.8% (89.2-95.3) | 91.5% (87.7-94.7) |
| Within 2 s | 93.9% (92.6-95.3) | 95.3% (93.7-96.7) | 95.1% (93.6-96.8) | 94.6% (91.4-96.9) |
| dur_ratio p50 / p90 (target p90 1.0) | 0.98 / 1.42 | 0.91 / 1.17 | 0.85 / 1.11 | 0.84 / 1.09 |
| Backlog p95 | 1535 ms (1063-2043) | 844 ms (414-1307) | 1191 ms (443-2667) | 1690 ms (421-4588) |
| Skips per 10 min (target 1) | 7.1 (0-17.9) | 7.8 (0-35.8) | 9.5 (0-32.7) | 19.7 (0-44.8) |
| Lines at 1.3x / 1.4x, of about 185 | 46 / 0 | 24 / 0 | 8 / 15 | 9 / 16 |
| First audio p50 / p95 | 2408 / 3924 ms | 2627 / 4403 ms | 2651 / 4686 ms | 2618 / 4746 ms |
| Copied voice | 97.4% | 96.1% | 94.8% | 95.6% |
| Translation p50 | 537 ms | 661 ms | 714 ms | 701 ms |

- Spread of equal runs (standard deviation): within 0.25 s 4.2 points (off), 2.1 (budget), 0.9 (controller);
  within 1 s 2.5-2.9 points. The 17-20 point gain within 0.25 s is far outside it; the 5-6 point gain within 1 s
  is about two standard deviations; budget vs controller vs engine speed are inside it.
- Per language, within 0.25 s off -> budget: Punjabi 68.7% -> 83.3%, Tamil 58.2% -> 77.8%. dur_ratio p90 with the
  controller: Punjabi 1.05, Tamil 1.17.
- Phrases more than 1 s late because they queued behind a long dub: 8.9% -> 2.2-3.2%. Those whose own audio arrived
  late stayed at 4.6-5.8% (long utterances the recogniser gives out only at their end; stalls).
- Skips come in bursts behind stalls: none in 11 of 20 runs; 9, 7, 10 and 24 of the skips came within twelve
  phrases of a stall.
- Cost: 15-18% fewer letters said (Punjabi 3.55 -> 2.91, Tamil 3.72 -> 3.08 letters a source word); every second
  line asked for twice. Words heard back (40 lines a cell): Punjabi 87.7% -> 80.1%, Tamil 84.4% -> 82.9%. Meaning,
  20 lines read: Punjabi 2 lost something that mattered, Tamil 7.
- No tolerance (`V1_BUDGET_OVER=1.0`, 3 runs each): dur_ratio p90 1.07 against 1.10, median 0.84 -> 0.78: every
  line shorter, the tail not moved. Default stays 1.15.
- Engine speed acted on 6.6 lines a run, all Tamil (Punjabi in this voice is at 229 ms a word, under the 320 ms
  floor); no timing number moved; words heard back 89.3% (33 lines) against 87.9% (33 lines sped by tempo only).

Against the targets: within 1 s 90% **reached** with the budget (7 of 10 runs at 90% or more, the rest
89.2-89.8%); dur_ratio p90 1.0 **not reached** (best 1.09-1.11); 1 skip per 10 min **not reached** in any setting.

## Caveats

- A loop of one 24.9 s reel: the same 11-12 phrases eight times. Nothing about a speaker who changes pace over ten
  minutes, or a speaker with pauses (the 62% and 76% videos of 24 Nov left only numbers, no audio).
- Two languages only; voice learned from the stream only; no stock voice, no Streamer Mode, no hosted engine.
- Nobody has heard 1.4x. Meaning was judged by a non-native reader on 20 lines a language.
- The breakers and ladder (EXP-023) were off; stalls decide the skips.
- First 6 s of silence were needed: speech fed before the speech-to-text socket opens reaches it in one burst and
  is stamped as 27 words in a 1 s slot (found, not fixed).

## Decision taken

`V1_LIVE_BUDGET` on for Punjabi and languages like it; the user's call for Tamil (content loss).
`V1_LIVE_RATECTRL` off until someone has heard 1.4x. `V1_LIVE_NATIVE_SPEED` off (ADR-0028). Next: two or three
dense real recordings of about 10 minutes (approval checklist).

## Links

- [docs/v1/LIVE_DENSE_REPORT.md](../../v1/LIVE_DENSE_REPORT.md)
- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "v1.1 WS1"
- `logs/sessions/ws1-*/`, `logs/trace/ws1-*/`
- Commits: `5ec5f4c`, `ce156a8`
- Related: [EXP-011](EXP-011-sync-stamps-and-hold.md), [EXP-013](EXP-013-steps-and-pace.md),
  [EXP-022](EXP-022-real-streams-24nov.md), [EXP-028](EXP-028-pitch-recording.md)
