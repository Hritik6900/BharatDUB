# EXP-031: Auto mode against "budget on" on the dense reel

- **Date:** 2026-11-26
- **Status:** done
- **Decision:** ADR-0036 ([../adr/0036-auto-mode.md](../adr/0036-auto-mode.md))

## Question

v1.2 makes auto mode the default ([ADR-0036](../adr/0036-auto-mode.md)). On the densest material we have, is a
Live session in auto mode as good as the best setting v1.1 measured (manual mode with `V1_LIVE_BUDGET=true`,
[EXP-024](EXP-024-dense-speech-budget.md))? Where it is not, which part of auto mode is the cause?

## Hypothesis

None was written down before the runs. What was known beforehand, from one smoke session of the build (n = 1,
`docs/v1/PROGRESS.md` "v1.2 Part 2"): pure auto mode gives a `/live` session without a streamer profile stock
voices, and that session was far behind (0 of 38 lines within 1 s) in an hour when the hosted stock voice was slow.

## Setup

- **Material:** `reel25.mp4`, the 24.9 s Hindi reel of EXP-024, played 8 times with 0.4 s between and 6 s of
  silence first: 211.2 s fed per run, the speaker talking 89% of the time. A loop of one reel, not a person at a
  microphone.
- **Sessions:** `backend/eval/live_replay.py`, GPU engine, Punjabi + Tamil with a viewer on each, sync mode, the
  harness asks for the voice on the stream with the consent flag. **Hold fixed at 6 s** on every backend
  (`LIVE_SYNC_ADAPT=false`), as in EXP-024, so the hold cannot grow in one setting and not in another.
- **Four comparison backends** on the laptop (GPU through the tunnel), started with `scripts\v1\ab-server.ps1`:

  | Name here | Port | Mode | What it is |
  |---|---|---|---|
  | **budget on** | 8121 | manual, `V1_LIVE_BUDGET=true` | v1.1's best setting: the budget on every phrase, the voice learned from the stream, every other v1 flag off |
  | **auto** | 8120 | auto, no overrides | what v1 runs by default. A session without a streamer profile gets **stock voices** (`LIVE_STOCK_DEFAULT` is on the founder's always-on list), so the voice on the stream is not learned |
  | **auto, learned voice** | 8122 | auto, `live_stock_default: off` | auto mode with the voice learned from the stream, as in every v1.1 measurement |
  | **auto, learned voice, no breaker** | 8123 | auto, `live_stock_default: off`, `breaker: off`, `live_degrade: off` | added after round 1 to tell the auto budget and the guards apart from the breakers and the ladder |

- **Runs:** 5 a setting, taken in turn (budget, auto, auto learned, no breaker, budget, ...), one session at a
  time: the harness waits for each to end before the next starts, and asks v0 (8010), v1 (8110) and the four
  backends for live sessions before every run. 2026-11-26 13:27-14:46 UTC. 20 runs, 0 failed. The fourth backend's
  run 1 was made right after round 1 (13:41), not inside it.
- **Two runs repeated.** In auto runs 4 and 5 the laptop's connection stalled: the hosted speech-to-text gave no
  phrase for 12.3 s and 15.9 s (no other run has a gap over 4 s; the reel has none over 0.4 s) and the link
  detector recorded every GPU endpoint unreachable for 26.8 s and 20.4 s. They are marked and were run again as
  runs 6 and 7 (15:00-15:10 UTC), each beside one more "budget on" run. Both sets are reported.
- **Numbers** are the backend's own (`/api/live/sessions/<id>/metrics`, the trace); nothing is estimated by the
  harness. "Within" is counted over lines that were spoken and have a moment; a line skipped as too late is not in
  that share, so a second pair of rows counts the skipped lines as not on time.
- **The hosted stock voice was timed outside any session** ten times over the same hours (one long line a
  language each time, between runs) and once more at the end with 20 lines of a live phrase's length.

## Metrics

- **Within 0.25 s / 1 s:** share of spoken phrases whose dub starts that close to its video moment.
- **dur_ratio:** seconds of dub sent over the seconds of its source slot.
- **Skips per 10 min:** phrases not spoken because they would start more than 4 s late.
- **First audio:** end of a phrase's speech to its first dubbed sound.
- **Copied voice:** share of spoken lines in the speaker's copied voice.
- **Unspoken / no sound without a mark:** a line no voice could say, marked and logged (auto mode only), and a
  line with neither sound nor mark.
- **Script guard:** every translated line; failed = letters of another script; flagged = still so after one new
  translation.
- **Meaning sample:** every 3rd spoken line of a language while its budget is on, judged after it was spoken by the
  hosted language model against its source: "lost" (something that matters is missing), "shift" (it says something
  different). A sample and a model's opinion.
- **Words heard back:** share of a dubbed line's words the hosted speech-to-text returns.

## Results

All **measured**. Mean (lowest-highest run), 5 runs a column, as run.

### Both languages together

| Measure | Budget on (manual) | Auto | Auto, learned voice | Auto, learned voice, no breaker |
|---|---|---|---|---|
| Within 0.25 s | **79.1% (73.2-81.8)** | 66.3% (57.4-75.1) | 69.6% (55.7-80.8) | 74.2% (72.4-76.6) |
| Within 1 s | **90.0% (87.4-94.0)** | 82.4% (71.0-89.3) | 83.9% (72.1-90.9) | 88.5% (86.4-90.1) |
| Within 0.25 s, skipped lines counted as late | 78.7% (73.2-81.4) | 62.0% (47.4-73.4) | 67.1% (46.1-80.3) | 73.4% (70.9-76.6) |
| Within 1 s, skipped lines counted as late | 89.5% (86.4-93.5) | 77.3% (55.0-87.2) | 80.6% (59.7-89.5) | 87.6% (85.2-89.6) |
| dur_ratio p50 | 0.91 (0.89-0.93) | 0.87 (0.79-0.90) | 0.86 (0.77-0.93) | 0.87 (0.81-0.91) |
| dur_ratio p90 | 1.16 (1.13-1.19) | 1.20 (1.17-1.22) | 1.15 (1.04-1.26) | 1.16 (1.09-1.24) |
| Lines longer than their slot | 31.7% (29.5-37.6) | 28.8% (20.6-32.6) | 25.8% (17.1-39.0) | 28.4% (20.5-36.0) |
| Skipped as too late, a run | 1.0 (0-2) | 11.4 (0-38) | 7.4 (1-29) | 1.8 (0-4) |
| Skips per 10 min | **3.0 (0-6.1)** | 34.1 (0-113.8) | 22.1 (3.0-86.6) | 5.4 (0-11.9) |
| First audio p50 (ms) | **2675 (2532-2778)** | 2980 (2834-3466) | 2965 (2623-3556) | 2767 (2685-2838) |
| First audio p95 (ms) | 4939 (4057-5769) | 5688 (4286-10486) | 5378 (4351-7714) | 4690 (4169-5095) |
| The session's first sound (ms after its first phrase ended) | 5296 (4970-5683) | 5402 (4494-6165) | 9045 (5238-23955) | 5547 (4811-6220) |
| Backlog p95 (ms) | 926 (630-1197) | 3278 (1146-5999) | 3002 (935-8248) | 1198 (910-1717) |
| Lines at the 1.3x limit | 27.6 (20-39) | 38.8 (27-58) | 39.8 (24-50) | 32.0 (29-35) |
| Lines spoken, of all lines | 186.2 of 187 | 175.2 of 187 | 184.2 of 192 | 185.8 of 188 |
| ... in the copied voice | 95.1% (92.2-96.8) | **0%** | 83.1% (50.9-97.3) | 97.0% (94.8-97.9) |
| Unspoken, marked and logged | not marked in manual mode | 1 line in the 5 runs (not translated, in a stalled run) | 0 | 0 |
| No sound and no mark | 0 | 0 | 0 | 0 |
| Spoken by another voice after the first one failed | does not happen in manual mode | 1 line in the 5 runs | 5.4 a run (0-18) | 0.4 a run (0-1) |
| Script guard: lines that failed / still wrong and flagged, a run (about 190 lines, every line checked) | not run | 7.2 (4-9) / 5.8 (3-7) | 5.0 (4-6) / 5.0 (4-6) | 3.2 (3-4) / 3.2 (3-4) |
| Transcript not in the source script (every phrase checked) | not run | 0 | 0 | 0 |
| Meaning sample: budgeted lines judged, a run | not run | 49.6 (41-56) | 55.0 (46-60) | 58.0 (53-60) |
| ... judged as lost | - | 11.4 (8-14) | 10.4 (8-14) | 8.6 (4-12) |
| ... loss rate | - | 23.3% (14.3-26.7) | 19.0% (15.0-25.9) | 14.8% (6.8-20.0) |
| Content shift found in the sample, a run | - | 7.6 (6-9) of 50.4 | 8.0 (4-13) of 55.4 | 6.6 (4-10) of 58.0 |
| Budget loosened by the meaning check, steps a run | - | 3.2 (2-4) | 2.4 (2-4) | 1.6 (0-2) |
| Budget tightened again, steps a run | - | 0.2 (0-1) | 0.4 (0-1) | 0.4 (0-1) |
| Share of lines translated under the budget | every line | 93.0% (78.7-97.4) | 94.1% (88.3-97.4) | 96.2% (94.3-96.9) |
| Shorter line asked for / used, a run | 73.8 / 70.2 | 86.6 / 81.6 | 89.8 / 86.4 | 90.8 / 88.8 |
| Translation p50 (ms) | 706 (673-741) | 765 (611-846) | 767 (655-833) | 759 (724-834) |
| Hold at the end | 6.0 s | 6.0 s | 6.0 s | 6.0 s |

"Budget on" repeats v1.1: EXP-024 had 80.6% (77.8-83.6) / 92.3% (89.8-96.1), dur_ratio p90 1.17, first audio p50
2627 ms for the same setting two days earlier.

**How much of the time the auto budget was on:** it came on once for each language in every auto session, at the
median 13-15 s into the session (the reason given: the first lines were longer than their slots, or the dub was
behind; "dense" twice), and it **never went off again** in any of the 17 auto sessions: this reel never gives it a
reason to. So on this material auto budget is the budget on every line after the first ones, plus the controller,
the dense rules and the loosening. The lines translated in full are the first ones of a session and those of a
language after its third loosening step (3 of the 17 sessions reached it). What auto budget does on normal speech
was not measured: there is no such material.

### Auto with the two stalled runs replaced (runs 1, 2, 3, 6, 7)

| Measure | Auto, as run (1-5) | Auto, stalled runs replaced | Budget on, runs 6-7 beside them |
|---|---|---|---|
| Within 0.25 s | 66.3% (57.4-75.1) | 66.8% (57.4-81.9) | 78.8%, 77.5% |
| Within 1 s | 82.4% (71.0-89.3) | 82.1% (71.0-92.3) | 91.3%, 92.1% |
| Skips per 10 min | 34.1 (0-113.8) | 25.1 (0-113.8) | 0, 3.0 |
| First audio p50 / p95 (ms) | 2980 / 5688 | 2950 / 5600 | 2503, 2642 / 4085, 4413 |
| dur_ratio p90 | 1.20 | 1.19 | 1.22, 1.16 |

Replacing the stalled runs changes nothing. Pure auto's seven runs range from 57.4% to 81.9% within 0.25 s and
from 71.0% to 92.3% within 1 s: run 7 (81.9% / 92.3%, 1 skip) is as good as "budget on", run 1 (38 skips) is far
behind. "Budget on" stayed within 73.2-81.8% and 87.4-94.0% over its seven runs.

### Per language (5 runs as run)

| Measure | Budget on | Auto | Auto, learned voice | Auto, learned voice, no breaker |
|---|---|---|---|---|
| Punjabi within 0.25 s | 81.4% (78.3-84.8) | 62.2% (47.8-78.4) | 74.3% (56.3-83.3) | 78.1% (73.1-81.9) |
| Punjabi within 1 s | 90.6% (86.5-94.6) | 81.7% (70.0-92.0) | 88.3% (74.6-94.4) | 90.3% (87.1-94.7) |
| Punjabi dur_ratio p90 | 1.11 (1.08-1.13) | 1.24 (1.17-1.35) | 1.09 (1.02-1.18) | 1.12 (1.04-1.20) |
| Punjabi skipped, a run | 0 | 5.0 (0-20) | 3.0 (0-15) | 0.4 (0-2) |
| Punjabi first audio p50 (ms) | 2771 (2645-2878) | 3093 (2888-3484) | 3017 (2719-3522) | 2876 (2721-2927) |
| Tamil within 0.25 s | 76.7% (68.1-81.2) | 70.6% (62.7-79.5) | 64.7% (52.8-78.2) | 70.2% (64.1-74.1) |
| Tamil within 1 s | 89.3% (84.6-93.5) | 83.2% (70.1-91.0) | 79.2% (67.4-91.2) | 86.8% (83.7-89.1) |
| Tamil dur_ratio p90 | 1.22 (1.17-1.26) | 1.14 (1.08-1.21) | 1.20 (1.09-1.34) | 1.23 (1.16-1.35) |
| Tamil skipped, a run | 1.0 (0-2) | 6.4 (0-18) | 4.4 (1-14) | 1.4 (0-4) |
| Tamil first audio p50 (ms) | 2560 (2447-2668) | 2801 (2584-3401) | 2839 (2397-3560) | 2655 (2581-2777) |
| Punjabi meaning sample: lost of judged (5 runs together) | not run | 30 of 121 (24.8%) | 24 of 143 (16.8%) | 19 of 147 (12.9%) |
| Tamil meaning sample: lost of judged (5 runs together) | not run | 27 of 127 (21.3%) | 28 of 132 (21.2%) | 24 of 143 (16.8%) |
| Punjabi script guard failed (5 runs together) | not run | 5 | 0 | 0 |
| Tamil script guard failed (5 runs together) | not run | 31 | 25 | 16 |

### Every run

| Run | Setting | Within 0.25 s | Within 1 s | dur_ratio p90 | Skipped | First audio p50 (ms) | Copied voice | Meaning: lost of judged | Loosening steps (language: step at second) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | budget on | 79.6 | 89.2 | 1.15 | 1 | 2716 | 94.8% | - | - |
| 1 | auto | 61.1 | 71.0 | 1.18 | 38 | 3467 | 0% | 10 of 41 | pa 1 at 82, ta 1 at 158 |
| 1 | auto, learned | 55.7 | 72.1 | 1.04 | 29 | 3556 | 50.9% | 8 of 46 | ta 1 at 81, pa 1 at 195, ta back to 0 at 203 |
| 1 | no breaker | 76.6 | 86.4 | 1.13 | 0 | 2685 | 97.9% | 4 of 59 | none |
| 2 | budget on | 81.0 | 94.0 | 1.19 | 1 | 2532 | 96.2% | - | - |
| 2 | auto | 57.4 | 76.7 | 1.22 | 0 | 2846 | 0% | 12 of 45 | pa 1 at 52, ta 1 at 60, pa 2 at 95, pa 3 at 137, ta back to 0 at 181 |
| 2 | auto, learned | 66.5 | 80.8 | 1.26 | 2 | 2717 | 97.3% | 14 of 54 | pa 1 at 89, ta 1 at 93, ta 2 at 142, ta 3 at 174 |
| 2 | no breaker | 73.5 | 90.1 | 1.12 | 1 | 2830 | 96.3% | 11 of 58 | pa 1 at 57, ta 1 at 58, pa back to 0 at 180 |
| 3 | budget on | 81.8 | 91.2 | 1.18 | 1 | 2651 | 95.7% | - | - |
| 3 | auto | 65.1 | 86.3 | 1.17 | 1 | 2902 | 0% | 8 of 56 | ta 1 at 60, pa 1 at 75, ta 2 at 98, pa 2 at 107 |
| 3 | auto, learned | 73.8 | 90.9 | 1.16 | 3 | 2928 | 94.3% | 9 of 60 | ta 1 at 82, ta 2 at 133 |
| 3 | no breaker | 72.4 | 89.7 | 1.23 | 4 | 2839 | 97.9% | 8 of 60 | pa 1 at 52, pa 2 at 94 |
| 4 | budget on | 79.9 | 87.4 | 1.13 | 2 | 2779 | 92.2% | - | - |
| 4 | auto (connection stalled) | 72.7 | 88.8 | 1.20 | 14 | 2850 | 0% | 13 of 52 | pa 1 at 78, ta 1 at 91, pa 2 at 118 |
| 4 | auto, learned | 71.3 | 86.2 | 1.18 | 2 | 3003 | 77.8% | 11 of 58 | pa 1 at 56, ta 1 at 171, pa back to 0 at 179 |
| 4 | no breaker | 75.3 | 87.3 | 1.09 | 4 | 2785 | 94.8% | 8 of 53 | ta 1 at 65, ta 2 at 145 |
| 5 | budget on | 73.2 | 88.0 | 1.15 | 0 | 2698 | 96.8% | - | - |
| 5 | auto (connection stalled) | 75.1 | 89.3 | 1.22 | 4 | 2834 | 0% | 14 of 54 | pa 1 at 52, ta 1 at 55, ta 2 at 92 |
| 5 | auto, learned | 80.8 | 89.3 | 1.13 | 1 | 2623 | 95.1% | 10 of 57 | ta 1 at 131, pa 1 at 185 |
| 5 | no breaker | 73.1 | 89.2 | 1.24 | 0 | 2697 | 97.9% | 12 of 60 | pa 1 at 54, pa back to 0 at 175, ta 1 at 197 |
| 6 | budget on | 78.8 | 91.3 | 1.22 | 0 | 2503 | 97.3% | - | - |
| 6 | auto | 68.3 | 84.2 | 1.23 | 2 | 2727 | 0% | 12 of 47 | pa 1 at 53, pa 2 at 91, pa 3 at 137, ta 1 at 171 |
| 7 | budget on | 77.5 | 92.1 | 1.16 | 1 | 2642 | 96.7% | - | - |
| 7 | auto | 81.9 | 92.3 | 1.17 | 1 | 2812 | 0% | 11 of 56 | pa 1 at 96 |

## Where auto is worse, and why

Three things in auto mode make it worse than "budget on" here, each with its evidence. The fourth column of the
tables is auto mode with the first two taken away.

### 1. Stock voices on `/live` (`LIVE_STOCK_DEFAULT`, always on)

This is the largest cause, and it is what the founder's list asks for.

- The pure-auto session speaks every line in a hosted stock voice (copied voice 0%). The hosted account takes
  one request at a time, and two languages need two lines for every phrase (a phrase every 2.2 s here).
- **A line in a stock voice is late wherever it occurs.** Over the five runs of each setting:

  | Lines that were timed | In the copied voice: within 1 s | In a stock voice: within 1 s |
  |---|---|---|
  | Budget on | 91.4% of 879 | 48.3% of 29 (the lines before the voice is learned) |
  | Auto | none | 82.9% of 812 |
  | Auto, learned voice | 87.2% of 756 | 65.8% of 111 |
  | Auto, learned voice, no breaker | 89.4% of 883 | 52.6% of 19 |

- **The wait for the voice.** From a line's translation to its first sound (the voice's own time and the wait for
  its turn): copied voice p50 790-818 ms, p90 1186-1488 ms, p95 1502-1898 ms in the three settings that have it;
  stock voice in pure auto p50 981 ms, p90 2098 ms, p95 3592 ms, 37 of 876 lines over 4 s, the longest 20.1 s.
  Our voice engine's own time was 463-465 ms a line at the median and never over 1 s (2518 lines).
- **The hosted voice's speed changed through the afternoon.** One long line a language, asked outside any session
  ten times between 13:27 and 14:45 UTC: Punjabi (5.3-5.6 s of sound) took 1.12-7.30 s from the ask to the last
  piece, Tamil (4.0-4.2 s of sound) 0.76-3.77 s; the build's smoke check an hour earlier saw 4.5 s and 7.1 s. Twenty
  lines of a live phrase's length (1.8 s of sound) at 15:09 UTC took 0.43-1.09 s each (medians 0.73 s and 0.50 s
  in two passes of ten). At that speed two languages keep the one request busy about half the time; when a line
  takes more than about 1.1 s, lines queue, and phrases that would start more than 4 s late are skipped.
  That is why pure auto ranges from 38 skipped lines (run 1, the slow hour) to 1 (run 7).
- The budget itself also cuts harder with a stock voice: Punjabi lines had 2.51 target letters per source word in
  pure auto against 3.03 with "budget on" and 2.84-2.87 in the two auto settings with the learned voice (the
  stock voice speaks Punjabi more slowly, so the same slot holds fewer letters), and the judge found more Punjabi
  lines that lost meaning (24.8% of 121 against 12.9% of 147 without stock voices).
- The gain that was expected from a voice that is ready at the first word did not show: the session's first sound
  came 5.4 s (4.5-6.2) after its first phrase ended in pure auto against 5.3 s (5.0-5.7) with "budget on".

### 2. The breakers and the ladder on this link (`V1_BREAKER`, `V1_LIVE_DEGRADE`, always on)

- In the "auto, learned voice" sessions the circuits of our voice engines opened **13 times in 3 of the 5 runs**:
  11 times because one health answer took longer than the probe's 2 s, twice because one line took longer than
  4 s. Twelve of the thirteen kept the engine unasked for 33.9-36.3 s (one closed again after 0.5 s). The ladder
  stepped from the copied voice to the stock voice 3 times and stayed there 78.8 s (run 1, twice) and 40.2 s
  (run 4): 119 s of the 1056 s fed. 22 lines were spoken by the stock voice after the engine's turn failed (14 of
  them "every engine's circuit is open").
- **The engine was not slow.** Its own time per line in those five sessions was 465 ms at the median and at most
  616 ms (756 lines). What was slow was the answer coming back over the link.
- **The same link without a breaker costs a few late lines.** In the two settings without breakers, over the same
  hours: 3 of 886 and 4 of 901 lines in the copied voice waited more than 4 s for their sound, and 2 lines fell to
  the stock voice after a broken connection. No ladder, no half minute in another voice.
- So a hiccup of the link of a few seconds, which manual mode rides out, takes the copied voice away for half a
  minute in auto mode and puts both languages on the hosted voice, which then queues (cause 1). The runs show it:
  copied voice 50.9% in run 1 (55.7% within 0.25 s, 29 skipped) and 77.8% in run 4, against 94.3-97.3% in runs 2,
  3 and 5.
- With the breakers and the ladder off, auto mode with the learned voice is steady: 72.4-76.6% within 0.25 s,
  86.4-90.1% within 1 s, 0-4 skipped. **That setting has no protection in a real stall** (EXP-023: 4 of 22
  phrases dubbed through a 50 s stall without them, all with them). The breakers were measured for a link that is
  gone for 50 s; this is the first measurement of what they do on a link that only hiccups.

### 3. The meaning check loosens the budget in almost every session

- A language's budget was loosened at least once in **16 of the 17 auto sessions** (all but run 1 without the
  breaker), the first time 52-131 s into the session on 6 to 12 judged lines. With 6 lines the rule ("over 25%
  lost") fires at 2 lost lines.
- The judge calls 15-19% of budgeted lines "lost" before any loosening when the voice is the learned one (step 0:
  Punjabi 13 of 84 and 17 of 95, Tamil 14 of 95 and 12 of 63, in the two settings with the learned voice). A rule
  that fires at 2 of 6 against a base rate of about 1 in 6 fires mostly on chance.
- **What a loosened budget does** (lines under the budget in the five "no breaker" runs, by how far the language
  was loosened at that moment):

  | | Step 0 | Step 1 | Step 2 |
  |---|---|---|---|
  | Punjabi: lines / dur_ratio p90 / longer than the slot | 269 / 1.05 / 16% | 133 / 1.20 / 40% | 55 / 1.19 / 45% |
  | Punjabi: within 0.25 s / 1 s | 81% / 90% | 78% / 92% | 72% / 89% |
  | Punjabi: judged as lost | 13 of 84 (15%) | 5 of 44 (11%) | 1 of 19 (5%) |
  | Tamil: lines / dur_ratio p90 / longer than the slot | 304 / 1.23 / 25% | 113 / 1.26 / 29% | 29 / 1.20 / 46% |
  | Tamil: within 0.25 s / 1 s | 72% / 89% | 69% / 86% | 82% / 96% |
  | Tamil: judged as lost | 14 of 95 (15%) | 9 of 38 (24%) | 1 of 10 (10%) |

  A loosened language has more lines longer than their slots (Punjabi 40-45% against 16%, Tamil 29-46% against
  25%); its judged loss is lower at step 2 (few lines); within 1 s does not move, within 0.25 s falls in Punjabi. This is the trade the rule was
  built to make. It is why auto with the learned voice and no breaker sits about 5 points under "budget on" within
  0.25 s (74.2% against 79.1%; four of the five "budget on" runs are above every one of its runs) while within 1 s
  the two overlap (88.5% and 90.0%).
- A step back was taken 5 times in the 15 sessions of runs 1-5, each about 2 minutes after a step up. In 3.5
  minutes a session cannot show whether the rule settles or goes back and forth.

### Also seen

- **The laptop's connection stalled twice** (auto runs 4 and 5: no phrase from the hosted speech-to-text for 12.3 s
  and 15.9 s, every GPU endpoint down for 26.8 s and 20.4 s). During the first, 14 lines were skipped, one line
  was not translated in Tamil (marked `untranslated`, logged: the one unspoken line of this work) and translation
  went to the hosted model for 12 phrases. Both runs were repeated.
- **The script guard's second translation does not help in Tamil.** 72 Tamil lines failed it in the 15 sessions of
  runs 1-5 (3 to 8 a session; the same few lines of the reel each loop: a Hindi word left in Devanagari inside the
  Tamil line), and the new translation was right for 3 of them; 69 were spoken as they were and flagged. Punjabi:
  5 failed, 4 put right. Our voice engine does not read letters of another script, so such a word is not said
  properly. The guard reports the fault; it does not remove it.
- **No line was without sound and without a mark** in any setting, and the only unspoken line is the one above.
  A stock line that timed out was asked once more and spoken, twice (in pure auto during the first stall, and
  the first line of one session with the learned voice).

## Words heard back

20 lines a language from runs 3 and 4 of each setting (40 lines a cell, as EXP-024), each heard once by the hosted
speech-to-text. "As counted in v1.1" is the rule EXP-024 used; "corrected rule" is Studio's rule of 25 Nov
(`nfc-2`: one spelling of every letter, and a word whose letters are there with the spaces set aside counts),
worked out from the same hearing.

| | Budget on | Auto (stock voices) | Auto, learned voice | Auto, learned voice, no breaker |
|---|---|---|---|---|
| Punjabi, corrected rule (run 3, run 4) | 91.3% (86.5, 96.1) | 86.4% (84.7, 88.0) | 88.9% (91.2, 86.6) | 87.0% (88.4, 85.7) |
| Tamil, corrected rule | 86.3% (83.2, 89.4) | 83.5% (83.1, 84.0) | 83.8% (78.6, 89.1) | 87.1% (91.6, 82.6) |
| Punjabi, as counted in v1.1 | 86.2% (83.0, 89.4) | 82.7% (82.2, 83.2) | 84.0% (87.1, 80.8) | 83.1% (85.1, 81.1) |
| Tamil, as counted in v1.1 | 85.3% (83.2, 87.3) | 79.7% (78.4, 80.9) | 83.3% (78.6, 88.1) | 83.1% (87.5, 78.6) |
| Lines under half, Punjabi / Tamil (corrected rule) | 1 / 1 | 0 / 1 | 2 / 2 | 1 / 2 |

For scale, EXP-024 (as counted in v1.1, 40 lines a cell): flags off 87.7% / 84.4%, budget + controller 80.1% /
82.9%. The two runs of one cell differ by up to 10.5 points here, so the 2-5 points between "budget on" and the
auto settings are not shown to be a difference. Nothing here says auto is clearer; the stock voice is not heard
back better than the copied one.

## Meaning, 20 lines a language

Read as in EXP-024: 20 consecutive lines of run 3 (phrases 37 to 56, the fourth and fifth loop of the reel), each
caption against its source line, counted when something that matters is missing ("myself", "at least", "again
and again", "mixed in", a clause) or a word is wrong. **Read by the author of this report, who is not a native
speaker of Punjabi or Tamil**: the same reader and the same rule as EXP-024's "7 of 20". Beside it, the session's
own judge (the hosted language model, one call per 20 lines) on the same lines: lost or shifted.

| Lines of 20 that lost something or say something wrong | Budget on | Auto (stock voices) | Auto, learned voice | Auto, learned voice, no breaker |
|---|---|---|---|---|
| Punjabi, read | 4 | 9 | 4 | 3 |
| Tamil, read | 7 | 6 | 10 | 10 |
| Punjabi, the model judge | 1 | 5 | 3 | 0 |
| Tamil, the model judge | 5 | 8 | 8 | 3 |
| Loosening steps in force on those lines, Punjabi / Tamil | not in manual mode | 1 then 2 / 1 then 2 | 0 / 1 | 1 then 2 / 0 |

- "Budget on" reads as in v1.1: Tamil 7 of 20 (v1.1: 7 of 20 with budget + controller), Punjabi 4 (v1.1: 2).
- **Auto does not lose less meaning than "budget on" in these lines.** Tamil with the learned voice: 10 of 20 in
  both auto settings against 7. Punjabi with stock voices: 9 of 20 against 4. Where a language had been loosened to
  step 2 (Punjabi in the no-breaker run from its sixth line on) the lines read complete: 3 of 20, all three before
  the step.
- The reader and the model judge disagree on how many (the judge is the more lenient: Tamil without the breaker 3
  against 10) and agree on the order for Punjabi. Neither is a speaker of the language. One stretch of one run
  each.

## Caveats

- One reel in a loop, two languages, one afternoon, the laptop behind the tunnel. Pure auto's result depends on the
  hosted voice's speed in that hour more than on anything in our code.
- The auto budget never went off: its "normal speech gets the full translation" half was not exercised.
- The hold was fixed at 6 s. In the product the hold may grow (and since v1.2 come back); auto mode with a
  growing hold was not measured. Fewer lines would be skipped and viewers would sit further behind.
- The fourth setting was added after round 1; its first run is 2-13 minutes later than the others of round 1.
- No English, no streamer profile, no hosted engine: the English voice choice, a stored voice and the probe were
  not exercised here.
- The meaning judge is a model on a sample; the meaning read is 20 lines of one run by a non-native reader;
  words heard back is 40 lines a cell.
- Thresholds were not changed and nothing was tuned between runs.

## Decision taken

None by the build. The defaults are the founder's list and stay as they are. What the numbers ask of the founder
is in `docs/v1/NEEDS_APPROVAL.md` item 29: whether `/live` keeps stock voices, what the breakers do on a link
that only hiccups, and how many judged lines the meaning check needs before its first step.

## Links

- [EXP-024](EXP-024-dense-speech-budget.md) (the v1.1 measurement of the same reel), [EXP-023](EXP-023-link-stalls-breaker.md)
  (the breakers in a 50 s stall), [EXP-020](EXP-020-v1-live-flags.md) (the earlier stock-voice runs),
  [EXP-032](EXP-032-auto-mode-studio.md) (auto mode in Studio)
- Code: `backend/app/v1/mode.py`, `dense.py`, `meaning.py`, `guards.py`, `breaker.py`, `degrade.py`,
  `voicechain.py`; harness `backend/eval/live_replay.py`, `live_judge.py`
- Run data: `data-v1/eval/v12/p3/` and `data-v1/ab/p3-*/` on the build laptop (not in git);
  `logs/sessions/index.csv` rows `p3-budget`, `p3-auto`, `p3-auto-learned`, `p3-auto-learned-nobrk`
