# EXP-007: Copied voice live: hosted clone vs IndicF5 on own GPU

- **Date:** 2026-11-14
- **Status:** done
- **Decision:** ADR-0010 ([../adr/0010-indicf5-own-gpu-voice.md](../adr/0010-indicf5-own-gpu-voice.md))

## Question

The hosted voice clone kept only 5 of 21 phrases in the copied voice in sync mode (EXP-006). Can our own IndicF5 engine
on an A100 speak every Indian target language in the speaker's voice and keep up live?

## Hypothesis

Not recorded; implied: an engine that takes about a second a line and makes several lines at once removes the
one-request limit and keeps nearly every phrase in the copied voice.

## Setup

- Engine: IndicF5 (337 M parameters) + Vocos, NFE 12, bf16, on the A100 40 GB GPU VM (address in
  `docs/v1/NEEDS_APPROVAL.md`); three engine processes on ports 9001-9003 behind an SSH tunnel; switch
  `GPU_VOICE_URL`; English and any failure go to the hosted voices.
- Voice sample: last 7 s before the first pause (at least 3.5 s), only with stream-voice consent; Prisma transcribes
  the exact cut; English words in the target script for the engine.
- Data: the dense 24.9 s Hindi reel, sync mode, voice learned from the stream, three loops. Backend on the laptop.
  One run per row.

## Metrics

- Phrases in the copied voice, out of spoken phrases.
- **Hold**, **behind** p50 / p95, skipped ([GLOSSARY](../GLOSSARY.md)).
- **Words heard back**: share of the dub's words that Prisma transcribes back ([GLOSSARY](../GLOSSARY.md)).
- Engine time per line, on the machine and from the laptop.

## Results

Live, **measured**, 2026-11-14, one run per row (LIVE_TEST_REPORT.md "The speaker's own voice, live"):

| Run | In the copied voice | Hold | Behind p50 / p95 | Skipped | Words heard back |
|---|---|---|---|---|---|
| Hosted clone, Tamil (afternoon) | 5 of 21 | 14.5 s | 1.2 s / 2.6 s | 0 of 38 | not checked |
| GPU engine, Tamil | 31 of 32 | 7.5 s | 1.3 s / 3.2 s | 2 of 37 | 80% |
| GPU engine, Tamil + Bengali + Telugu | 30-31 of 31 each | 9 s | 0.4-1.1 s / 2.8-3.2 s | 1 of 34 | 85% Bengali, 89% Telugu |

Engine, **measured**, 2026-11-14 (SPEC section 16; gpu_engine README):

| What | Time |
|---|---|
| One line on the machine | 0.91 s, whatever its length |
| One line from the laptop | 1.2-1.7 s (about 0.45 s a request through the tunnel) |
| Three lines at once, three processes | 1.19 s (three replicas in one process: 2.26 s) |
| Hosted clone line | 1.9-3.5 s, not streamed |

- Engine speed setting: at 1.3x the engine kept 70% of words (Prisma, 14 Tamil lines); normal speed then `atempo` 82%;
  untouched 80%. So the engine speaks at 1.0 and the fit stays with `atempo`. **measured**, 14 lines.
- Opus instead of raw PCM saved about 0.5 s a line. **measured**, n not recorded.
- A two-word English phrase in Latin letters came out as noise; the same words in Tamil letters came out word for word. **measured**, one line.
- Voice ready about 9 s into the stream.

## Caveats

- Two earlier runs of the same setup skipped 3 and 6 phrases: results move with network and APIs.
- How close the voice sounds to the speaker was not judged by ear (see EXP-012).
- The hosted-clone row ran in a slow afternoon; the GPU rows in the evening.

## Decision taken

Copied voice in Live comes from IndicF5 on our GPU (pool of three processes); hosted stock voices for English and as
fallback (ADR-0010). This is our own engine, chosen because it measured best.

## Links

- [LIVE_TEST_REPORT.md](../../../LIVE_TEST_REPORT.md) "The speaker's own voice, live"
- [SPEC.md](../../../SPEC.md) section 16 ("Live copied voice on our own GPU engine", 2026-11-14 evening)
- [gpu_engine/README.md](../../../gpu_engine/README.md) "Measured 14 Nov 2026"
- Commits: `770112f` (IndicF5 behind `GPU_VOICE_URL`), `d911d2a` (pool of three engines, Opus), `7fba6ab`
  (voice sample from short lines, reconnecting tunnel)
- Related: [EXP-006](EXP-006-sync-mode.md), [EXP-009](EXP-009-voice-engine-tuning.md),
  [ADR-0011](../adr/0011-borrowed-a100-ssh-tunnels.md)
