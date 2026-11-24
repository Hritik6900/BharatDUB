# ADR-0014: Two engines (Standard hosted-first vs GPU) chosen per session/job by an Engine button

- **Status:** accepted
- **Date:** 2026-11-21
- **Superseded by:** —

## Context

On 21 Nov speech-to-text and translation were made to run on our GPU machine (ADR-0015). The first version was a
process-wide switch, `AI_MODE=gpu`, off by default (`cc7fd39`). A process-wide switch meant every session and job
on the backend changed together, and the hosted path (the default people used) could not be kept untouched while
the GPU path was tried.

## Options considered

| Option | Outcome |
|---|---|
| Global `AI_MODE` switch for the whole backend | first version (`cc7fd39`); kept only as the default for a caller that does not choose |
| Engine per Live session and per Studio job | **chosen** (`31673b9`) |
| Separate backends per engine | not recorded (not evaluated) |

## Decision

- An "Engine" button on `/live`, `/streamer` and `/studio`; `engine: "gpu"` on `POST /api/live/sessions` and
  `POST /api/jobs`. The button shows only when `GPU_STT_URL` and `GPU_LLM_URL` are set (`gpu_mode` in
  `/api/streamers/health`).
- A session stores its engine; a job keeps it in its meta file; `providers.get_stt/get_llm/get_tts/get_gpu_voice(engine)`
  hand out the matching provider; each engine has its own voice-engine client.
- The hosted engine (`cloud`, "Standard") is the default and is not touched.

## Consequences

### Good

- Checked on the site, one session each way, same reel (**measured** 21 Nov, `../../../SPEC.md` section 21):
  without the button the source lines came from the hosted service (35 of 35 in Devanagari, translation p50
  0.96 s); with it from the GPU (42 of 42 in Latin letters, translation p50 0.55 s).
- Both engines could be compared on the same backend (ADR-0016 measurements, v1 eval).
- v1's router reproduces both engines from one config file (ADR-0021).

### Bad

- Two paths to test and keep working; v1's tests had to stop reading the GPU addresses from the env file (`405abd8`).
- The GPU engine's source caption is Latin Hinglish, not Devanagari (SPEC section 21).
- A user has to know which engine to pick; no automatic choice exists.

## Evidence

- Experiments: [EXP-014](../experiments/EXP-014-standard-vs-gpu-engine.md)
- Commits: `cc7fd39` (all-GPU mode, `AI_MODE`), `31673b9` (engine per session and job), `405abd8` (tests)
- Sources: [`SPEC.md`](../../../SPEC.md) section 21; [`DISCOVERY.md`](../../v1/DISCOVERY.md) section 2
