# EXP-002: Demucs separation: laptop CPU vs A100

- **Date:** 2026-11-13
- **Status:** done
- **Decision:** none

Measured on three days: CPU on 2026-11-13, first GPU machine on 2026-11-15, second GPU machine on 2026-11-20.

## Question

Studio stage 3 (voice/music separation with Demucs `htdemucs`) was the slowest stage on the laptop. How much faster
is it on the A100, and are the stems the same?

## Hypothesis

Not recorded; implied: the GPU cuts separation time several-fold, and transfer over the tunnel, not compute, will
be the larger part.

## Setup

- Model: Demucs `htdemucs`, `--two-stems=vocals`.
- CPU: dev laptop (Ryzen 7 7435HS, torch 2.15 CPU), Demucs in a subprocess worker.
- GPU: `gpu_engine/sep_engine.py` on port 9010 of the A100 40 GB GPU VM (address in `docs/v1/NEEDS_APPROVAL.md`),
  reached from the laptop by SSH tunnel; switch `GPU_SEPARATE_URL`; CPU fallback on any failure.
- Input: 60 s of audio. Number of runs: not recorded beyond the ranges given.

## Metrics

- Wall-clock time to separate 60 s of audio, as seen by the backend on the laptop.
- Stem agreement: difference between GPU and CPU stems, in dB below the signal.

## Results

| Where | Date | Time for 60 s of audio | Label |
|---|---|---|---|
| Laptop CPU | 2026-11-13 | 40.3 s (SPEC section 16); 38.9 s in the 15 Nov comparison (gpu_engine README) | measured |
| First GPU machine, through the tunnel | 2026-11-15 | 11.5-13.8 s (1.5 s on the A100; the rest is sending 2.4 MB and receiving 4.3 MB of FLAC) | measured |
| Second GPU machine, through the tunnel | 2026-11-20 | 4.0-4.8 s (1.5 s on the GPU) | measured |

- Stems: GPU and CPU stems differ by -40 dB (difference 40 dB below the signal). **measured**, 2026-11-15.
- In a whole Studio job (24.9 s reel, 4 languages, stock voices, nothing cached, 2026-11-13) Demucs on CPU took 22.9 s
  of 84.9 s (README "Results", Studio). **measured**, one run.
- Silero VAD: 3.5 s for a 14 s clip including model load (SPEC section 16). **measured**, one run.

## Caveats

- n per row is not recorded; the GPU rows are ranges over an unrecorded number of runs.
- The two GPU rows are two different machines and network paths; why the second is faster through the tunnel is not
  broken down in the sources (unconfirmed: smaller transfer time on the new machine's link).

## Decision taken

Separation goes to the GPU when `GPU_SEPARATE_URL` is set, CPU otherwise. No ADR of its own; it follows ADR-0002
(providers behind interfaces, fail soft).

## Links

- [SPEC.md](../../../SPEC.md) sections 16 (Demucs on CPU; Studio separation on the GPU, 2026-11-15) and 17
  (GPU machine replaced, 2026-11-20)
- [gpu_engine/README.md](../../../gpu_engine/README.md) "Studio: Demucs on the GPU"
- [README.md](../../../README.md) "Results" (Studio, 13 Nov)
- Commits: `df1fa91` (Studio pipeline with Demucs worker), `60ee40b` (Demucs on the GPU machine), `0143cbd` (new
  machine)
- Related: [ADR-0011](../adr/0011-borrowed-a100-ssh-tunnels.md)
