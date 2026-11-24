# EXP-013: Denoising steps per voice kind; pace target 450 ms a word

- **Date:** 2026-11-21
- **Status:** partial
- **Decision:** none

## Question

(1) Do more denoising steps make the copied voice clearer, for a recorded voice and for a voice learned from the
stream? (2) A recorded voice was late on the dense reel (56% within 1 s). Does asking a slow copied voice to speak
faster, to a target pace, fix its timing?

## Hypothesis

Not recorded; implied: (1) 16 steps beat 12 on clarity at little time cost (an 8-line check said 71% -> 83%);
(2) the engine copies the sample's pace, which differs by language, so a per-language speed-up to about 450 ms a word
frees room without using up the 1.3x squeeze.

## Setup

- Engine: IndicF5 on the A100 GPU VM through the tunnel; steps sent with each line (`gpu_voice_steps` for a recorded
  voice, `gpu_voice_steps_stream` for a learned voice; 0 = the engine's 12).
- Pace: `gpu_voice_pace_ms` = 450, `gpu_voice_pace_max` = 1.5 (0 = off); pace measured per language on speech only,
  lines of 4 words and more.
- Data: the dense 24.9 s Hindi reel, six loops, hold fixed at 6 s. Steps: one run each, 12 vs 16. Pace: Streamer Mode,
  one recorded voice, Tamil + Punjabi, two runs off and two on. Engine-alone pace check: 16 lines a cell.

## Metrics

- **Words heard back** ([GLOSSARY](../GLOSSARY.md)), **first audio** p50, **on time** within 0.5 / 1 / 2 s.
- Phrases at the 1.3x squeeze limit; translator word limit for an 8-word phrase; ms a word.

## Results

Steps, **measured**, 2026-11-21, one run each, 12 -> 16 steps (SPEC.md section 20 "Denoising steps per kind of voice"):

| Voice | Lines a language | Words heard back | First audio p50 | Within 1 s |
|---|---|---|---|---|
| Recorded (casual 7.5 s sample), Tamil / Punjabi | about 68 | 67% -> 73% / 74% -> 82% | 2.7 s -> 2.9 s | 56% -> 56% |
| Learned from the stream, Tamil / Bengali | about 75 | 81% -> 77% / 78% -> 79% | 2.8 s -> 2.9 s | 87% -> 87% (within 2 s 97% -> 93%) |

The recorded voice was late at either setting: 26-27% within 0.25 s, 56% within 1 s; 96-98 of about 137 phrases at the
1.3x limit; 7 skipped. In the 8-line check it took 813 ms a word in Tamil vs 455-555 ms for the other recorded voice.

Pace, engine alone, **measured**, 16 lines a cell (SPEC section 20 "A copied voice that is slow in a language"):

| Tamil at engine speed | 1.0 | 1.25 | 1.5 |
|---|---|---|---|
| Words heard back | 84-85% | 83-85% | 82-84% |

Punjabi under 300 ms a word lost words in one of two voices (91% -> 85% -> 62%). Two recorded voices took 640-650 ms a
word in Tamil and 350-360 ms in Punjabi.

Pace, whole sessions, **measured**, two runs off / two runs on, about 63 Tamil phrases a run:

| Tamil | Off (run 1 / 2) | On (run 1 / 2) |
|---|---|---|
| Within 1 s | 58% / 55% | 75% / 65% |
| Within 0.5 s | 52% / 38% | 63% / 52% |
| At the squeeze limit | 42 / 41 | 31 / 34 |
| Words heard back | 79% / 73% | 73% / 74% |
| Word limit for an 8-word phrase | 3-4 | 5 |

Punjabi (not sped up in the clean run): within 1 s 56% / 60% and 68%, words 86% / 82% and 79%.

## Caveats

- **Two equal runs differ by about 10 points in timing and 6 in words heard back**, so one or two runs each way prove
  little.
- The first "on" run still counted silence as speech and so sped Punjabi up a little.
- The 8-line steps check (12 steps 71%, 16 steps 83%) overstated the gain.
- Not measured: a streamer speaking at their own normal pace (the real Streamer Mode case). On this reel (about 5 words
  a second) any natural-pace recorded voice starts only 57-72% of phrases within 1 s; the other recorded voice was as
  late (56-57%), so the cause is the reel's speed, not one slow sample.

## Decision taken

No ADR. `gpu_voice_steps` = 16 for a recorded voice, `gpu_voice_steps_stream` = 12 for a learned voice; pace target
450 ms a word on (switch `gpu_voice_pace_ms`).

## Links

- [SPEC.md](../../../SPEC.md) section 20 ("Denoising steps per kind of voice", "A copied voice that is slow in a
  language speaks faster")
- Commits: `b5807d0` (steps per voice kind), `e4bb35a` (pace target)
- Related: [EXP-010](EXP-010-voice-engine-speedup.md), [EXP-011](EXP-011-sync-stamps-and-hold.md),
  [EXP-012](EXP-012-clone-similarity.md)
