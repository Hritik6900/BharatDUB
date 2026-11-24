# EXP-012: How close the copied voice is (speaker similarity, words heard back)

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** none

## Question

In Streamer Mode, how close is the copied voice to the streamer's real voice, and how clear are its words?

## Hypothesis

Not recorded; implied: the copy is clearly closer to its own speaker than to anyone else, and clarity depends on the
stored sample.

## Setup

- Script: a test script kept outside the repository (scratch); 8 stream-style lines a language, translated by the
  live translator, spoken by the IndicF5 engine from the stored sample exactly as a session sends it.
- Two stored streamer profiles (same microphone and room): one with a slowly read sample, one with a 7.5 s sample of
  casual speech. Languages: Punjabi, Tamil, Bengali, Gujarati.
- Engines on the A100 GPU VM through the tunnel. One run for the first profile after repair (unconfirmed); two runs for the other.

## Metrics

- **Words heard back** ([GLOSSARY](../GLOSSARY.md)): Prisma hears each line back.
- Speaker similarity: cosine similarity of ECAPA2 speaker embeddings. Reference points on these recordings: the same
  real person against themselves 0.86-0.89; the two streamers against each other 0.67; an unrelated speaker about 0.
- Own-speaker check: is each line closer to its own speaker than to the other streamer?

## Results

All **measured**, 2026-11-21 (SPEC.md section 20 "How good is the copied voice in Streamer Mode"). 8 lines a language.

| Profile / state | Words heard back | Similarity | Closer to own voice |
|---|---|---|---|
| Profile 1, stale stored text (before repair) | 53-73% | 0.57-0.58 | not given |
| Profile 1, after repair | Punjabi 91%, Tamil 87%, Bengali 91%, Gujarati 98% | 0.63-0.70 | 32 of 32 |
| Profile 2 (7.5 s casual sample), two runs | Punjabi 74-89%, Tamil 68-72%, Bengali 75-88%, Gujarati 65-82% | 0.69-0.76 | 64 of 64 |

- Stale text effect: lines at 250-300 ms a word instead of 455-555 ms. **measured**.
- Worst single lines 0-29%; the same line can come out well in one run and badly in the next (new random start each
  time). **measured**.

## Caveats

- 8 lines a language is a small sample (EXP-013 found an 8-line check overstated a gain).
- ECAPA2 is licensed CC-BY-NC-4.0; it was later rejected for product use (ADR-0025). The scale differs from the 0.87
  other vendors quote (different model and test).
- No human listening test.
- Profile 1's broken text was written by a repair script while the server ran; the server wrote its old copy back
  (INC-03, [../INCIDENTS.md](../INCIDENTS.md)).

## Decision taken

No ADR. `voice_ref.sample_text` now checks the stored text length against the file wherever a stored voice goes to the
engines, re-transcribes and corrects the profile when they differ. Rule recorded: never write the local store from a
script while the server runs. Verdict: the copy carries who is speaking but is not the same voice (0.63-0.76 vs
0.86-0.89).

## Links

- [SPEC.md](../../../SPEC.md) section 20 ("How good is the copied voice in Streamer Mode")
- Commits: `86188e5` (sample text checked against its file; 53% -> 91% words heard back)
- Related: [EXP-008](EXP-008-streamer-mode-first.md), [EXP-013](EXP-013-steps-and-pace.md),
  [ADR-0012](../adr/0012-streamer-mode-recorded-voice.md), [ADR-0025](../adr/0025-speaker-model-licence.md)
