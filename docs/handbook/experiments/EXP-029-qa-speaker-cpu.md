# EXP-029: QA server speaker comparison on CPU (WS5)

- **Date:** 2026-11-25
- **Status:** partial
- **Decision:** ADR-0025 ([../adr/0025-speaker-model-licence.md](../adr/0025-speaker-model-licence.md))

## Question

The speaker-similarity figures measured on 21 Nov used ECAPA2, which is CC-BY-NC-4.0 (non-commercial). Can the QA
server compare speakers on CPU, with no GPU memory, using a model open to commercial use, fast enough to score a
Studio take?

## Hypothesis

SpeechBrain's ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`, Apache-2.0) runs on a laptop-class CPU in well under
a second per comparison and separates the same speaker from another voice.

## Setup

- Laptop CPU (Ryzen 7 7435HS), 4 threads, no CUDA device visible, SpeechBrain 1.1.2 with torch CPU. Built on branch
  `v1-ws5` beside another workstream that was using the GPU; nothing run on the GPU machine.
- Clips cut from the eval reel (7 s and 3 s) and one other voice (7 s).
- 1 run of 20 comparisons per row; one pair each for the similarity values.

## Metrics

Time per comparison (mean, range), similarity of same speaker vs another voice, first model load time.

## Results

All **measured**, 2026-11-25. Source: [PROGRESS.md "v1.1 WS5"](../../v1/PROGRESS.md),
[MODELS.md](../../v1/MODELS.md).

| What | Runs | Result |
|---|---|---|
| One comparison, two clips of 7 s | 1 run, 20 comparisons | mean 765 ms, range 727-797 |
| The same, two clips of 3 s | 1 run, 20 | mean 378 ms, range 343-440 |
| Another voice, 7 s each | 1 run, 20 | mean 752 ms, range 700-831 |
| Similarity, same speaker | one pair each | 0.883 (7 s), 0.765 (3 s) |
| Similarity, another voice | one pair | 0.142 |
| Model load, first time with download | 1 | 38.8 s |

- The QA server now loads a speaker model only when it is listed as checked and open to commercial use, refuses
  ECAPA2 and unlisted models, and says so in `/health`; it still scores words without a similarity.
- Found: SpeechBrain's config reader fails with ruamel.yaml 0.19; the QA requirements pin below it.

## Caveats

- Laptop CPU, not the GPU machine's CPU; one run; one same-speaker pair and one other-voice pair.
- This scale is not ECAPA2's: the 21 Nov figures (real person against themselves 0.86-0.89, copy 0.63-0.76) do not
  carry over. No similarity threshold is set (`V1_HQ_SIMILARITY_MIN=0`) until the scale is measured on real takes.
- The QA server's Whisper half, the server on the VM and its memory were not run (they need the machine).
- Similarity is not likeness to a listener: nobody has listened.

## Decision taken

The QA server uses the Apache-2.0 speaker model on CPU; ECAPA2 is refused unless `QA_SPK_ALLOW_NONCOMMERCIAL=1` for a
measurement that does not ship (ADR-0025). Deploying the QA server on the VM is in the approval checklist.

## Links

- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "v1.1 WS5"
- [docs/v1/MODELS.md](../../v1/MODELS.md), "QA server's speaker model"
- [gpu_engine_v1/qa_server.py](../../../gpu_engine_v1/qa_server.py)
- Commits: `ddb8d59` (branch `v1-ws5`), merged as `df27b93`
- Related: [EXP-012](EXP-012-clone-similarity.md), [ADR-0025](../adr/0025-speaker-model-licence.md),
  [ADR-0033](../adr/0033-deploy-kit-4gb-rule.md)
