# EXP-009: Voice engine tuning: letters not bytes, sample length, denoise steps

- **Date:** 2026-11-20
- **Status:** done
- **Decision:** ADR-0010 ([../adr/0010-indicf5-own-gpu-voice.md](../adr/0010-indicf5-own-gpu-voice.md))

## Question

On the replaced GPU machine the copied voice came out slow and long (Tamil 9 words -> 18 s of audio). Why, and which
engine settings (line sizing, sample length, denoising steps, CUDA MPS) give clear speech fast enough for Live?

## Hypothesis

Not recorded; implied: the engine sizes a line by its sample's text, so a text in another script or a too-long sample
mis-sizes every line; fewer denoising steps save time with little loss of clarity.

## Setup

- New A100 40 GB GPU VM (address in `docs/v1/NEEDS_APPROVAL.md`), engines rebuilt from `gpu_engine/`
  (`setup_machine.sh`, new `voice_engine_live.py`, bf16), three processes, CUDA MPS on or off.
- Line check: 10 lines spoken by the engine and heard back by Prisma, per step count.
- Live: the dense 24.9 s Hindi reel, sync mode, voice learned from the stream, Tamil + Bengali; Streamer Mode with a
  stored voice, Punjabi + Bengali. Backend on the laptop, engines through the tunnel. One run each.

## Metrics

- Engine time per line, alone and three at once.
- **Words heard back** ([GLOSSARY](../GLOSSARY.md)) per line set.
- Live: phrases in the copied voice, **first audio**, **behind**, voice step time per phrase, **hold**.

## Results

**measured**, 2026-11-20 (SPEC.md section 17; gpu_engine README).

CUDA MPS (three processes):

| Lines at once | Without MPS | With MPS |
|---|---|---|
| 1 | 1.0 s | 0.9 s |
| 2 | 2.1 s | 0.95 s |
| 3 | 3.2 s | 1.1 s |

Line sizing and sample length:

| Fix | Before | After |
|---|---|---|
| Speed corrected to letters, not UTF-8 bytes (Latin-letter sample text made Indic lines 3x too long) | Tamil 9 words -> 18 s, 30% heard back | 9.0 s, 100% |
| `speech_cut` counts all speech, caps at wanted length + 2 s | a quiet mic gave a 15.7 s sample | near 7 s |

Denoising steps (10 lines each):

| Steps | Time per line | Words heard back |
|---|---|---|
| 12 | 905 ms | 97% |
| 10 | 744 ms | 97% |
| 8 | 601 ms | 96% |
| 6 | 455 ms | 89% |

Live after tuning (10 steps), one run each:

| Run | In the copied voice | First audio p50 / p95 | Behind p50 / p95 | Voice step | Hold |
|---|---|---|---|---|---|
| Live, voice from stream, Tamil + Bengali (before tuning) | 31 of 33, 32 of 34 | 3.9 / 4.7 s | 0.1-0.3 s / 1.8-2.5 s | 1.85 s | 9.5 s |
| Live, voice from stream, Tamil + Bengali (after) | 33 of 33, 31 of 31 | 3.1-3.2 s / 3.8-3.9 s | 0.2-0.4 s / 1.8-3.5 s | 1.2-1.3 s | 9 s |
| Streamer, stored voice, Punjabi + Bengali (after) | 34 of 34, 29 of 31 | 3.2-3.3 s | 0 s / 1.7-2.8 s | not given | not given |

- Separation on the new machine: 60 s of audio in 4.0-4.8 s (EXP-002).
- A request through the tunnel cost a median 410 ms though the network round trip was 170 ms; not solved.

## Caveats

- One run per Live row; 10 lines per step count.
- How natural 8 steps sounds was not judged by ear.
- The Streamer row was later found to use a stale stored text (lines twice too fast), so its "behind p50 0 s" is too
  kind (SPEC section 20; EXP-012).
- The "before tuning" first-audio numbers come from SPEC section 17's "before tuning 3.9 / 4.7" note; that they
  belong to the same run as the other "before" numbers in that row is (unconfirmed).

## Decision taken

Engines run at 10 steps (`NFE` in `start_live.sh`), speed computed per letter, sample cut capped near 7 s, MPS on.
Steps went back to 12 on 2026-11-21 when the engine got faster (EXP-010).

## Links

- [SPEC.md](../../../SPEC.md) section 17 ("GPU machine replaced", "Voice engine tuned")
- [gpu_engine/README.md](../../../gpu_engine/README.md) "MPS matters"
- Commits: `0143cbd` (new machine, MPS), `59dbb97` (letters, sample cut, 10 steps)
- Related: [EXP-007](EXP-007-copied-voice-hosted-vs-gpu.md), [EXP-010](EXP-010-voice-engine-speedup.md),
  [ADR-0011](../adr/0011-borrowed-a100-ssh-tunnels.md)
