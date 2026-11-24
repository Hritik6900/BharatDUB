# ADR-0025: ECAPA2 speaker-similarity rejected (CC-BY-NC-4.0); Apache-2.0 speechbrain ECAPA on the QA server

- **Status:** accepted
- **Date:** 2026-11-23
- **Superseded by:** —

## Context

"How close is the copied voice to the speaker" was measured on 21 Nov with ECAPA2 speaker embeddings: copied voice
0.63-0.76, the same real person against themselves 0.86-0.89 (`../../../SPEC.md` section 20). Studio HQ and the QA
server need a similarity score (ADR-0024). On 23 Nov the model pages were checked for licences
(`../../v1/MODELS.md`).

## Options considered

| Option | Licence (from its page) | Outcome |
|---|---|---|
| `Jenthe/ECAPA2` | CC-BY-NC-4.0, non-commercial | **rejected** for the product; refused by the QA server since 25 Nov |
| `speechbrain/spkrec-ecapa-voxceleb` (ECAPA-TDNN) | Apache-2.0 tag, not gated; commit `0f99f2d0...` last changed 18 Feb 2025 | **chosen** |
| WavLM-based models | named as an example in `../../v1/ARCHITECTURE.md` | not evaluated |

## Decision

- The QA server (:9045) uses SpeechBrain ECAPA and runs on CPU.
- Since 25 Nov the server loads a speaker model only if it is listed in `SPK_LICENCES` (`qa_server.py`) as checked
  and open to commercial use; ECAPA2 and unlisted models are refused, `/health` says why, and words are still
  scored. `QA_SPK_ALLOW_NONCOMMERCIAL=1` lifts it for a measurement that ships nothing (`../../v1/MODELS.md`, WS5).
- No similarity threshold until the new scale is measured on our voices (`V1_HQ_SIMILARITY_MIN=0`).

## Consequences

### Good

- CPU run (**measured** 25 Nov, laptop CPU, 4 threads, one run, 20 comparisons a row): two 7 s clips 765 ms
  (727-797); two 3 s clips 378 ms (343-440). Same speaker 7 s cuts 0.883, 3 s cuts 0.765, another voice 0.142,
  one pair each: the scale has room between "same" and "other" (`../../v1/MODELS.md`). No GPU memory needed.

### Bad

- Earlier similarity figures (0.63-0.76 / 0.86-0.89) do not carry over to the new scale; the real-person baseline
  must be measured again.
- The training data (VoxCeleb) states no licence on its page; whether that limits the weights is a legal question
  this check cannot settle (`../../v1/NEEDS_APPROVAL.md` item 24).
- Only the licence tag was read, not the licence text.
- The QA server has not run on the VM (item 4); the Whisper half of it was not run.

## Evidence

- Experiments: [EXP-012](../experiments/EXP-012-clone-similarity.md), [EXP-029](../experiments/EXP-029-qa-speaker-cpu.md)
- Commits: `bb71d9a` (QA server with SpeechBrain ECAPA), `ddb8d59`/`df27b93` (licence guard)
- Sources: [`MODELS.md`](../../v1/MODELS.md) "Findings" 1 and the WS5 section; [`SPEC.md`](../../../SPEC.md) section 20;
  [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) items 4, 24
