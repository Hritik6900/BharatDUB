# ADR-0010: Copied voice via IndicF5 on our own GPU (3 processes, CUDA MPS); hosted stock voices for English and fallback

- **Status:** accepted
- **Date:** 2026-11-14
- **Superseded by:** —

## Context

The hosted voice clone (Gnani `vachana-vc-v1`) is not streamed and took 1.9-3.5 s per line, against about 0.5 s to
first chunk for a stock voice (**measured** 13 Nov, `../../../SPEC.md` section 16). The account allows one request
at a time. In sync mode with the voice learned from the stream only 5 of 21 spoken phrases came out in the copied
voice and the hold grew to 14.5 s (**measured** 14 Nov, SPEC section 16).

## Options considered

| Option | Measured | Outcome |
|---|---|---|
| Hosted clone (`vachana-vc-v1`) in Live | 5 of 21 phrases copied, hold 14.5 s (14 Nov) | kept for Studio and as a fallback |
| Stock voices only | ~0.5 s to first chunk, not the speaker's voice | kept for English and fallback |
| IndicF5 (337 M parameters + Vocos) on an A100 we run | Tamil: 31 of 32 copied, hold 7.5 s; Tamil + Bengali + Telugu: 30-31 of 31 each, hold 9 s (14 Nov) | **chosen** |
| Indic-Mio as a second voice | tried 21 Nov (ADR-0017) | switch only |

## Decision

- IndicF5 on our GPU (`GPU_VOICE_URL`, `providers/tts_gpu.py`, `gpu_engine/`) speaks every Indian target language
  in the copied voice. English and any failure go to hosted voices. Empty `GPU_VOICE_URL` = hosted only.
- Three engine processes (9001-9003). Separate processes run in parallel, replicas in one process do not: three
  lines at once 1.19 s against 2.26 s (14 Nov). With CUDA MPS on the replacement machine: 3 lines 3.2 s -> 1.1 s
  (**measured** 20 Nov, SPEC section 17).
- The engine reads only the language's own letters, so the live prompt writes English words in the target
  script for GPU languages.

## Consequences

### Good

- Engine speed-ups were ours to make: line length in letters not bytes (20 Nov: a Tamil 9-word line 18 s -> 9.0 s,
  words heard back 30% -> 100%); batched guidance 742 -> 366 ms at 10 steps; MP3 transport; one line from the
  laptop 1.33 s -> 0.79 s (21 Nov, SPEC section 17).
- No per-line vendor fee and no one-request limit on the voice.

### Bad

- The engine copies the sample's pace and microphone: a rushed sample makes a rushed dub; a 15.7 s sample made
  lines slow (SPEC section 17). Samples must stay near 7 s.
- Short lines of 2-4 words are often swallowed (ADR-0017). No English (MODELS: "11 Indian languages, no English").
- Copied voice is not the same voice: ECAPA2 similarity 0.63-0.76 against 0.86-0.89 for the real person (21 Nov,
  SPEC section 20; that scale is non-commercial, ADR-0025).
- A GPU machine to run and reach (ADR-0011). Licence MIT, terms: copy only voices you have permission for
  (`../../v1/MODELS.md`).

## Evidence

- Experiments: [EXP-007](../experiments/EXP-007-copied-voice-hosted-vs-gpu.md), [EXP-009](../experiments/EXP-009-voice-engine-tuning.md),
  [EXP-010](../experiments/EXP-010-voice-engine-speedup.md), [EXP-012](../experiments/EXP-012-clone-similarity.md)
- Commits: `770112f`/`b674dca` (IndicF5 behind `GPU_VOICE_URL`), `d911d2a`/`89e8bc7` (pool of three), `0143cbd`
  (new machine, MPS), `59dbb97` (letters not bytes), `ada2272` (batched guidance, MP3)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 16, 17, 20; [`MODELS.md`](../../v1/MODELS.md);
  [pitch PDF](../../../pitch/BharatDub_Architecture_Costs_Questions.pdf) (15 Nov, "Why our own GPU for the voice")
