# Live on dense speech: what was built, what it measured (v1.1 WS1, 24 Nov 2026)

Why: on real videos (24 Nov, Punjabi) the share of phrases whose dub starts within 0.25 s of its video moment
fell from 95% to 76% when the speaker talked 76% of the time instead of 62%, the 1.3x speed limit was hit on
16-40% of lines, and a longer viewer hold had not helped before. The dubbed line is longer than the time the
speaker took, so every line starts later than the one before it.

Everything here is behind three flags that are off by default. With them off the pipeline is v0's (a test holds
that). Every number below was measured in this work; where something was not measured it says so.

## 1. Short answer

On the densest material this machine has (one 24.9 s reel played eight times in a row: the speaker talks 89% of
the time, 5.1 words a second), five runs per setting, Punjabi and Tamil together:

| | flags off | budget | budget + controller | + engine speed |
|---|---|---|---|---|
| Dub starts within 0.25 s of its moment | 63.5% (57.9-68.6) | 80.6% (77.8-83.6) | **83.1% (81.9-84.4)** | 82.8% (80.5-85.9) |
| ... within 1 s (target 90%) | 86.5% (84.2-90.6) | 92.3% (89.8-96.1) | 91.8% (89.2-95.3) | 91.5% (87.7-94.7) |
| Dub length / slot, p90 (target 1.0) | 1.42 (1.37-1.47) | 1.17 (1.15-1.22) | 1.11 (1.06-1.15) | 1.09 (1.02-1.15) |
| Lines longer than their slot | 47.9% | 32.3% | 20.1% | 18.4% |
| Lines at the speed limit (1.3x, or 1.4x in dense mode) | 46 of 185 | 24 of 185 | 23 of 188 | 25 of 183 |
| Phrases skipped as too late, per 10 min (target 1) | 7.1 (0-17.9) | 7.8 (0-35.8) | 9.5 (0-32.7) | 19.7 (0-44.8) |

Mean (lowest-highest run). Against the targets:

- **Within 1 s at 90% or more: reached** with the budget, with or without the controller (mean 91.8-92.3%;
  7 of the 10 runs were at 90% or more, the other three at 89.2-89.8%). Flags off: 86.5%, 1 run of 5 at 90%.
- **Dub length / slot at p90 no more than 1.0: not reached.** 1.42 came down to 1.11 (Punjabi 1.05, Tamil 1.17).
  What is left is named in section 5: Tamil lines of one to three words, and the 15% the check lets through.
- **No more than 1 skipped phrase in 10 minutes: not reached, in no setting.** Skips come in bursts: none in 11 of
  the 20 runs, 5 to 15 in others. They follow a stall (a line whose text or audio took many seconds to arrive),
  which a shorter dub cannot prevent. The settings cannot be told apart on this number.

What it costs: the translation is shorter (3.0 letters per source word instead of 3.6, section 6), a translation
takes 0.18 s longer at the median because every second line is asked for twice, and in Tamil a third of the lines
that were read had lost something that mattered. Recommendation in section 8.

## 2. What was built

| Part | Flag | What it does |
|---|---|---|
| `dur_ratio` and `backlog` | none (written with the trace, or with one of the flags below) | per phrase and language: seconds of dubbed audio sent over the seconds of its source slot, and how far the dub queue was behind the video when the phrase's turn came. In the trace, on `/metrics-ui` (p50 / p90 per language, backlog p95), in a session's `/metrics`, in the stream watcher's summary, in `logs/sessions/` |
| Expansion model | used by the two flags below | per language and kind of voice: ms of dubbed speech per target letter, per target word and per source word, a running average over the lines spoken, started from `backend/config/live_expansion.json` |
| Duration budget | `V1_LIVE_BUDGET` | the translator is given the phrase's own slot as words and letters, a compact spoken register, "keep names and numbers". The answer's expected duration is checked; more than 15% over: one request for a shorter line (2.5 s at most), used when it is shorter and well formed |
| Rate control | `V1_LIVE_RATECTRL` | a PI controller on the backlog scales that budget (1.0 down to 0.6, back within seconds once the backlog is gone). Dense mode when the speaker talked more than 70% of the last 30 s: budget at most 0.9 of the slot, lines under 3 words join the next, speed-up up to 1.4x |
| Engine speed | `V1_LIVE_NATIVE_SPEED` | a line that must be shorter is asked from our voice engine up to 1.2x faster, never under 320 ms a word; the rest by tempo as before |
| Replay harness | none (a tool) | `backend/eval/live_replay.py`: a recording's sound and clock into Live in real time, settings in turn, mean and spread |

How the budget relates to v0's. v0 already had a word limit (`live_length_budget` with `live_brief`): words =
source words x the speaker's average pace x a share / the dubbing voice's ms a word, the share 1.15 in step,
0.9 once the dub is 0.5 s behind, 0.6 once it is 2 s behind; nothing checks the answer. `V1_LIVE_BUDGET` replaces
that limit for every phrase it can plan and leaves it in place for the others (a language whose voice has no
rate yet, until its first line of four words was spoken). The differences: the slot is the phrase's own measured
span, not the average pace; the aim is 1.0 times the slot, not 1.15; the limit is given in letters as well as
words (Tamil says in 4 words what Punjabi says in 7); the answer is checked against letters x ms a letter and
asked for again once; a line that arrives late gets the time left until the next phrase is due, not its whole
slot; and the three steps become the controller's continuous scale. Nothing else of v0 is changed: the playhead
(`_playhead`) is where the backlog is read from, the 1.3x tempo fit (`live_fit*`) and the skip rule
(`live_skip_after_ms`, 4 s in sync mode) work as before (1.4x only in dense mode), and the copied voice's pace
(`gpu_voice_pace_ms`) is untouched: the model learns the pace the voice really speaks at.

Native duration: v0's voice engines (9001-9003) take `speed` per line and nothing else (`DISCOVERY.md`); the
library's `fix_duration` is not exposed. `V1_LIVE_NATIVE_SPEED` therefore turns the wanted duration into a speed
(expected duration from the model / the room) and asks for that. Nothing was changed or deployed on the engines.

## 3. Where the expansion model's numbers come from

- `logs/sessions/` (v0 and v1 since 13 Nov) has **no field with the dub's length**. `audio_ms` is the time
  between the first and the last audio message: about 0 for a line our engine sends in one piece. The length can
  be worked out only for a phrase whose successor queued straight behind it (the successor's `heard` time minus
  this one's, times this one's `tempo`): 2,162 such phrases in the groups of 20 and more. That gives ms per source word and nothing about the
  target text: Punjabi 266 ms (763 phrases), Tamil 231 ms (622), Bengali 195 ms (257), copied voice on our engine.
  These lean to the long side (only lines that made the next one wait are counted).
- The v1 trace had `tts_chars` (characters of the text, spaces included) but no duration either.
- So ms per letter and per word did not exist anywhere. From now on every spoken phrase stores `dub_ms`,
  `dub_raw_ms` (at the voice's own pace), `slot_ms`, `tgt_words`, `tgt_chars`. The seed file was built from the
  first flags-off run of this work: Punjabi 57.8 ms a letter, 229 ms a word (46 lines); Tamil 56.1 ms a letter,
  360 ms a word (38 lines). Rebuilt from the five flags-off runs of section 4 it would read 57.3 / 229 (449
  lines) and 54.4 / 333 (357 lines). **Both are the pace of one voice: the one learned from this reel's speaker.**
  Another voice has another pace; the session's first lines count for more than the seed and replace it.
- A language without a seed (all but Punjabi and Tamil) starts on v0's word limit and switches to the budget
  after its first line of four words.

How good the model is, on the 921 lines of the five controller runs: spoken duration / expected duration is 0.90
at p10, 1.00 at p50 and 1.08 at p90 in Punjabi; 0.81, 0.97 and 1.07 in Tamil.

## 4. The measurement

**Material.** `data-v1/eval/reel25.mp4`, a 24.9 s Hindi reel of one speaker with no pause, played 8 times with
0.4 s of silence between and 6 s of silence before the first word: 211 s fed per run. Measured over the runs:
the speaker talks **89% of the time** (the real videos of 24 Nov: 62% and 76%), 273 source words a minute over
the whole run, **5.1 words a second inside a phrase**, a median phrase of 9 words in 1.7 s. **This is a loop of
one reel:** the same 11-12 phrases eight times. It says how the pipeline holds up under speech with no pause; it
says nothing about a speaker who changes pace or topic over ten minutes. **No long real recording exists on
this machine** (Live audio is never stored; the densest long session in the logs, 62% speaking over 16 minutes,
left only its numbers). A request for two or three recordings is in `NEEDS_APPROVAL.md` item 19.

**Setup.** GPU engine, Punjabi and Tamil with a viewer on each, voice learned from the stream (with the consent
flag), sync mode, hold fixed at 6 s (`LIVE_SYNC_ADAPT=false` on every backend, so the hold cannot grow in one
setting and not in another), every other v1 flag off. Four comparison backends on ports 8111-8114, runs taken in
turn (off, budget, controller, engine speed, off, ...), one session at a time, no stream live on 8010 or 8110 at
any start. 20 runs, 0 failed, 0 errors reported by the sessions. The backend's own numbers
(`/api/live/sessions/<id>/metrics` and the trace); nothing estimated by the harness.

The 6 s of silence at the start are there because a session's speech-to-text connection takes a few seconds to
open: speech fed before that reaches it in one burst and is stamped as 27 words in a 1 s slot, which spoiled the
first phrases of this work's trial runs in a different way each time, in every setting. It is not fixed; a real
stream that begins talking in its first second has it.

### Both languages together (mean, lowest-highest of 5 runs)

| Measure | off | budget | budget + controller | + engine speed |
|---|---|---|---|---|
| First audio p50 (ms) | 2408 (2308-2496) | 2627 (2517-2749) | 2651 (2453-2786) | 2618 (2514-2798) |
| First audio p95 (ms) | 3924 (3607-4364) | 4403 (3773-5078) | 4686 (3883-6849) | 4746 (3984-6901) |
| Within 0.25 s | 63.5% (57.9-68.6) | 80.6% (77.8-83.6) | 83.1% (81.9-84.4) | 82.8% (80.5-85.9) |
| Within 1 s | 86.5% (84.2-90.6) | 92.3% (89.8-96.1) | 91.8% (89.2-95.3) | 91.5% (87.7-94.7) |
| Within 2 s | 93.9% (92.6-95.3) | 95.3% (93.7-96.7) | 95.1% (93.6-96.8) | 94.6% (91.4-96.9) |
| dur_ratio p50 | 0.98 (0.97-1.00) | 0.91 (0.89-0.93) | 0.85 (0.83-0.87) | 0.84 (0.82-0.84) |
| dur_ratio p90 | 1.42 (1.37-1.47) | 1.17 (1.15-1.22) | 1.11 (1.06-1.15) | 1.09 (1.02-1.15) |
| Lines longer than their slot | 47.9% (46.6-49.1) | 32.3% (28.2-34.8) | 20.1% (16.8-23.3) | 18.4% (14.0-20.9) |
| Backlog p50 (ms) | 59 (1-139) | 0 | 0 | 0 |
| Backlog p95 (ms) | 1535 (1063-2043) | 844 (414-1307) | 1191 (443-2667) | 1690 (421-4588) |
| Skipped as too late, a run | 2.4 (0-6) | 2.6 (0-12) | 3.2 (0-11) | 6.6 (0-15) |
| ... per 10 minutes | 7.1 (0-17.9) | 7.8 (0-35.8) | 9.5 (0-32.7) | 19.7 (0-44.8) |
| Lines sped up at all | 99 (85-107) | 55 (46-62) | 39 (35-46) | 38 (35-40) |
| Lines at 1.3x | 46 (35-57) | 24 (21-29) | 8 (5-11) | 9 (8-10) |
| Lines at 1.4x (dense mode only) | 0 | 0 | 15 (9-18) | 16 (14-18) |
| Lines spoken, of them in the copied voice | 185, 97.4% | 185, 96.1% | 188, 94.8% | 183, 95.6% |
| Translation p50 (ms) | 537 (515-563) | 661 (608-727) | 714 (646-784) | 701 (641-769) |
| First answer over its budget by more than 15% | not budgeted | 44% | 53% | 53% |
| Shorter line used | - | 37% | 46% | 45% |
| Budget scale, mean | - | 0.95 | 0.88 | 0.88 |
| Lines the engine was asked to speak faster | - | - | - | 6.6 a run (5-8), all Tamil |

Spread of equal runs (standard deviation over the 5): within 0.25 s 4.2 points with the flags off, 2.1 with the
budget, 0.9 with the controller; within 1 s 2.5-2.9 points in every setting. The 17-20 point gain within 0.25 s
is far outside that; the 5-6 point gain within 1 s is about two standard deviations; the differences between
budget, controller and engine speed are inside it.

### Per language

| Measure | off | budget | budget + controller | + engine speed |
|---|---|---|---|---|
| Punjabi within 0.25 s | 68.7% (63.2-77.1) | 83.3% (78.4-86.7) | 85.7% (83.2-88.7) | 86.2% (85.1-88.5) |
| Punjabi within 1 s | 88.8% (86.2-92.7) | 92.5% (87.5-96.7) | 91.7% (89.3-95.9) | 91.5% (89.3-93.6) |
| Punjabi dur_ratio p50 / p90 | 1.01 / 1.40 | 0.92 / 1.11 | 0.87 / 1.05 | 0.86 / 1.04 |
| Punjabi lines at 1.3x / 1.4x | 17 / 0 | 10 / 0 | 3.8 / 6.2 | 4.0 / 5.8 |
| Tamil within 0.25 s | 58.2% (52.2-66.3) | 77.8% (75.8-80.5) | 80.6% (78.1-82.8) | 79.3% (75.6-83.2) |
| Tamil within 1 s | 84.2% (78.3-90.7) | 92.0% (89.2-95.6) | 91.8% (89.2-94.8) | 91.4% (86.1-95.7) |
| Tamil dur_ratio p50 / p90 | 0.95 / 1.44 | 0.88 / 1.21 | 0.81 / 1.17 | 0.80 / 1.20 |
| Tamil lines at 1.3x / 1.4x | 29 / 0 | 13.8 / 0 | 3.8 / 8.8 | 4.8 / 10.2 |

### Every run

| Run | Setting | Within 0.25 s | Within 1 s | dur_ratio p50 / p90 | Backlog p95 (ms) | Skipped | At 1.3x / 1.4x | First audio p50 (ms) |
|---|---|---|---|---|---|---|---|---|
| 1 | off | 57.9 | 84.2 | 0.98 / 1.38 | 1504 | 0 | 57 / 0 | 2324 |
| 1 | budget | 79.8 | 91.8 | 0.91 / 1.16 | 1307 | 0 | 21 / 0 | 2748 |
| 1 | controller | 81.9 | 89.4 | 0.84 / 1.12 | 2667 | 5 | 8 / 18 | 2786 |
| 1 | engine speed | 85.9 | 93.7 | 0.84 / 1.12 | 421 | 0 | 8 / 16 | 2798 |
| 2 | off | 65.6 | 84.7 | 0.97 / 1.47 | 1896 | 3 | 47 / 0 | 2496 |
| 2 | budget | 81.0 | 90.5 | 0.90 / 1.15 | 921 | 1 | 29 / 0 | 2737 |
| 2 | controller | 83.4 | 91.4 | 0.87 / 1.15 | 649 | 0 | 5 / 17 | 2772 |
| 2 | engine speed | 82.8 | 87.7 | 0.84 / 1.15 | 4588 | 15 | 10 / 18 | 2674 |
| 3 | off | 68.6 | 90.6 | 0.98 / 1.43 | 1063 | 0 | 42 / 0 | 2470 |
| 3 | budget | 77.8 | 89.8 | 0.92 / 1.17 | 501 | 0 | 26 / 0 | 2576 |
| 3 | controller | 84.4 | 93.5 | 0.85 / 1.06 | 443 | 0 | 11 / 9 | 2452 |
| 3 | engine speed | 81.3 | 94.7 | 0.84 / 1.07 | 545 | 0 | 10 / 15 | 2546 |
| 4 | off | 64.7 | 88.4 | 1.00 / 1.37 | 1169 | 3 | 35 / 0 | 2445 |
| 4 | budget | 80.7 | 96.1 | 0.93 / 1.22 | 414 | 0 | 22 / 0 | 2517 |
| 4 | controller | 83.4 | 95.3 | 0.84 / 1.13 | 511 | 0 | 9 / 16 | 2676 |
| 4 | engine speed | 83.7 | 89.3 | 0.82 / 1.02 | 1254 | 6 | 8 / 14 | 2514 |
| 5 | off | 60.6 | 84.6 | 0.99 / 1.46 | 2043 | 6 | 49 / 0 | 2308 |
| 5 | budget | 83.6 | 93.2 | 0.89 / 1.16 | 1076 | 12 | 21 / 0 | 2558 |
| 5 | controller | 82.6 | 89.2 | 0.83 / 1.09 | 1683 | 11 | 5 / 15 | 2566 |
| 5 | engine speed | 80.5 | 92.0 | 0.84 / 1.09 | 1641 | 12 | 8 / 17 | 2560 |

The records behind these tables are in `logs/sessions/ws1-*/` and `logs/trace/ws1-*/` (`ws1-ctl` also holds the
three controller runs of section 5, `ws1-native` one short check run).

## 5. What limits it

**Why phrases are still more than 1 s late.** Each late phrase is either queued behind an earlier dub that ran
long (the dub's length: what this work is about) or its own audio arrived late (the text or the voice took long).

| Phrases more than 1 s late | off | budget | budget + controller | + engine speed |
|---|---|---|---|---|
| All | 13.5% (9.4-15.9) | 7.7% (3.9-10.2) | 8.2% (4.7-10.8) | 8.5% (5.4-12.3) |
| ... queued behind an earlier dub | 8.9% | 2.2% | 3.2% | 2.7% |
| ... their own audio arrived late | 4.6% | 5.5% | 5.0% | 5.8% |

The budget takes the first cause from 8.9% to 2-3%. The second one it cannot touch, and it is now the larger:
(1) a few times a run the recogniser holds on to a long utterance (22-30 words, 5.5-6 s) and gives it
out only at its end, by which time its moment is 3 s in the past; such a line now gets the time that is left
and not its whole slot, so the phrase behind it no longer pays too; (2) stalls of the link or of a hosted
service: in run 5 the first line of the budget session took 16.8 s to its first audio and the eight phrases
behind it were skipped; in run 1 of the controller five translations in a row took 1.9-3.5 s instead of 0.7.

**Why skips are not at 1 in 10 minutes.** A phrase is skipped when it would start more than 4 s after its moment.
With the flags off 12 phrases were skipped in the 5 runs, with the budget 13, with the controller 16, with engine
speed 33 (out of about 940 phrase-languages each). 11 of the 20 runs had none. Of those skips 9, 7, 10 and 24
came within twelve phrases of a line whose text arrived more than 3 s late or whose audio took more than 6 s:
bursts behind a stall. The runs of round 5 had a burst in all four settings (6, 12, 11, 12). Nothing in this
work shortens a stall; the breakers and the ladder of WS0 are what acts on one, and they were off here.

**Why dur_ratio p90 is not at 1.0.** Of the 921 lines of the five controller runs, 186 were longer than their
slot (Punjabi 78 of 463, Tamil 108 of 458):

| Longer than its slot because | Punjabi | Tamil |
|---|---|---|
| a line of one to three words: our engine is asked to say such a line at 0.75 of the speed, or it swallows it (v0's guard, measured on 21 Nov) | 15 | 65 |
| inside what the check lets through (expected duration up to 1.15 times the budget) | 36 | 27 |
| the budget was larger than the slot (a span that was not believed, or under the 0.4 s floor) | 9 | 1 |
| a stock voice, before the copied voice was learned | 8 | 3 |
| still over after the second answer, or no shorter answer came | 5 | 7 |
| spoken in one call with the phrases behind it | 5 | 1 |
| the voice took over 15% longer than expected | 0 | 4 |

Tamil is the hard case: a source phrase of 6-7 words in 1.2 s leaves room for two or three Tamil words, and those
are exactly the lines the engine has to say slowly.

**Does a stricter check help?** Three more runs each, in turn, of the controller as above and the same with no
tolerance (`V1_BUDGET_OVER=1.0`): dur_ratio p90 1.07 (1.04-1.12) against 1.10 (1.06-1.15), Punjabi 1.03 against
1.01, Tamil 1.19 against 1.17; the median fell from 0.84 to 0.78, 131 instead of 92 lines a run were asked for
twice, translation p50 696 -> 834 ms; within 1 s 91.8% against 92.6%, within 0.25 s 84.8% against 82.6%. So no:
the tail is not moved, every line gets shorter. The default stays 1.15.

**Engine speed.** The engine was asked to speak faster on 6.6 lines a run, all of them Tamil: Punjabi in this
voice is at 229 ms a word, already under the 320 ms floor, so no Punjabi line qualifies. No timing number moved
(table above). Words heard back on those lines: 89.3% over 33 lines (mean 1.15x from the engine, 1.38x in all)
against 87.9% over 33 controller lines sped up by tempo alone to 1.15x and more (Tamil alone: 90.2% over 17). No
loss seen and no gain; with a floor that keeps the old finding in mind (the engine at 1.3x kept 70% of words on
14 Nov), it hardly ever acts.

## 6. What the shorter translation costs

| | off | budget | budget + controller |
|---|---|---|---|
| Target letters per source word, Punjabi | 3.55 | 3.02 | 2.91 |
| Target letters per source word, Tamil | 3.72 | 3.16 | 3.08 |
| Target words per source word, Punjabi / Tamil | 0.91 / 0.57 | 0.77 / 0.50 | 0.75 / 0.48 |
| Dub at the voice's own pace / slot (sums) | 1.06 | 0.91 | 0.86 |
| Dub as sent / slot (sums) | 0.95 | 0.86 | 0.81 |

So without the flags the dub is 6% longer than the speech over a whole run, and squeezed to 0.95; with the
controller it is 14% shorter before any squeeze. That is 15-18% fewer letters said.

**Words heard back** (the hosted speech-to-text hears a dubbed line, share of the line's words it returns; 20
lines a language from runs 3 and 4 of each setting, 40 lines a cell):

| | off | budget + controller |
|---|---|---|
| Punjabi | 87.7% (86.3, 89.0), 0 lines under half | 80.1% (76.0, 84.1), 3 lines under half |
| Tamil | 84.4% (82.7, 86.0), 0 under half | 82.9% (85.3, 80.4), 3 under half |

Tamil is the same. Punjabi is 7.6 points lower, a little more than two equal runs differ by (about 6); the
difference sits in short lines (5 lines of 3-4 words scored 60%, the 35 longer ones 82.9%; the flags-off sample
had no Punjabi line that short). A shorter line is a line the engine speaks less surely. 40 lines a cell is a
small sample.

**Meaning** (20 consecutive lines of run 3 with budget and controller, each against its source line; read by
the author of this report, who is not a native speaker of either language):

- Punjabi: 2 of 20 dropped something that mattered ("I eat it myself" lost "myself"; a 33-word line lost "at
  least" and "this way"); 3 more lost a small word ("other", "to you"); none said something wrong.
- Tamil: 7 of 20 dropped something that mattered: "mixed in" (what the other shops do) twice, "again and
  again" (the oil), "myself", a whole clause about the masala in the 33-word line, one line reduced to two
  garbled words, and one said "your family" for "my family" (a wrong word, not a cut). The flags-off Tamil of
  the same stretch (13 lines read) kept "at least", "mixed in" and "again and again".

So in Punjabi the budget mostly removed what could go; in Tamil, where the same idea needs longer words, it
removed content in about a third of the lines read. One stretch of one run each; no scorer, no native reader.

## 7. Not measured

- A real long recording, a real stream, a speaker with pauses (the 62% and 76% videos of 24 Nov): no audio exists.
- One viewer language alone, a stock voice, Streamer Mode with a stored voice (slower than a voice learned from a
  fast speaker, so the budget would bite harder), the hosted engine, any language but Punjabi and Tamil.
- Dense mode's three parts one by one (tighter budget, short lines joined, 1.4x); the join of short source lines
  hardly occurred (the reel has few lines under 3 words).
- How 1.4x sounds, how a copied voice sounds on shortened lines: no listener.
- Translation quality beyond the 40 lines read above.
- The flags together with WS0's breakers and ladder, or with `V1_PHRASE_DYNAMIC` (longer phrases would give fewer
  one-to-three-word Tamil lines, which is the largest remaining cause; not tried).
- The viewer's page: the numbers are the server's (`late`), not a browser's.

## 8. Recommendation

- `V1_LIVE_BUDGET` **on for Punjabi and languages like it**: 17 points more phrases within 0.25 s, 6 more within
  1 s, half as many lines at the speed limit, for 0.2 s of first audio and a translation 15% shorter. **For Tamil
  it is your call**: the timing gain is the largest there (58% -> 78% within 0.25 s) and so is the loss of content.
- `V1_LIVE_RATECTRL`: inside the spread against the budget alone on timing (83.1% against 80.6% within 0.25 s,
  91.8% against 92.3% within 1 s), a shorter dub still (dur_ratio p90 1.11 against 1.17), and it brings 1.4x on
  15 lines a run, which nobody has heard. **Off until someone listens to 1.4x**, or on with
  `V1_DENSE_MAX_TEMPO=1.3`. That variant was not measured.
- `V1_LIVE_NATIVE_SPEED`: **off**. No effect measured.
- First thing to do next: two or three real recordings (`NEEDS_APPROVAL.md` item 19), and the stalls: they, not the
  dub's length, now decide the skips and most of what is late.

## 9. How to repeat it

```powershell
# one window per backend
powershell -File scripts\v1\ab-server.ps1 -Port 8111 -Name m-off    -Flags "LIVE_SYNC_ADAPT=false"
powershell -File scripts\v1\ab-server.ps1 -Port 8112 -Name m-budget -Flags "LIVE_SYNC_ADAPT=false,V1_LIVE_BUDGET=true"
powershell -File scripts\v1\ab-server.ps1 -Port 8113 -Name m-ctl    -Flags "LIVE_SYNC_ADAPT=false,V1_LIVE_BUDGET=true,V1_LIVE_RATECTRL=true"
powershell -File scripts\v1\ab-server.ps1 -Port 8114 -Name m-native -Flags "LIVE_SYNC_ADAPT=false,V1_LIVE_BUDGET=true,V1_LIVE_RATECTRL=true,V1_LIVE_NATIVE_SPEED=true"
cd backend
.venv\Scripts\python.exe -m eval.live_replay ..\data-v1\eval\reel25.mp4 --out ..\data-v1\eval\ws1\main `
    --target off=http://127.0.0.1:8111 --target budget=http://127.0.0.1:8112 --target ctl=http://127.0.0.1:8113 `
    --target native=http://127.0.0.1:8114 --runs 5 --langs pa-IN,ta-IN --loops 8 --gap-ms 400 --keep-audio
.venv\Scripts\python.exe -m eval.live_judge ..\data-v1\eval\ws1\main\runs\off_r3 ..\data-v1\eval\ws1\main\runs\ctl_r3 --n 20
```

About 75 minutes for the 20 runs. Before these, 5 trial runs of 80-105 s were made to find faults and set the
controller (its integral first took a minute to let go, which cut every line to 0.7 of its slot for nothing; a
shorter line was asked for with too few words; a short line's slow speed was not counted; a late line kept its
whole slot). Their numbers are in none of the tables.
