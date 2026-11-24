# ADR-0015: GPU engine: Whisper-Hindi2Hinglish-Apex STT + Gemma 4 E4B on vLLM translation, hosted as fallback

- **Status:** accepted
- **Date:** 2026-11-21
- **Superseded by:** — (the order of hearing inside the GPU engine was reversed by [ADR-0016](0016-hosted-stt-first.md))

## Context

On 21 Nov the hosted speech-to-text failed every request for part of the day while its voices worked, and Live,
Studio transcription and new voice recordings all stopped with it (`../../../SPEC.md` section 20; INC-02). The
hosted account allows one request at a time. In hosted mode a phrase spent about 1.0 s in speech-to-text and
0.85-0.95 s in translation (SPEC section 21). The voice already ran on our A100 (ADR-0010).

## Options considered

| Option | Outcome |
|---|---|
| Stay hosted for speech-to-text and translation | kept as the Standard engine (ADR-0014) |
| Whisper-Hindi2Hinglish-Apex (Apache-2.0) on our GPU, decoded again every 0.3 s for partials | **chosen** for speech-to-text |
| Bigger Whisper models (large-v3-turbo, large-v3) | measured later the same night: not better (ADR-0016) |
| Gemma 4 E4B (Apache-2.0) on vLLM | **chosen** for translation |

## Decision

All-GPU engine (`providers/stt_gpu.py`, `llm_local.py`, `fallback.py`, `gpu_engine/stt_engine.py`): speech-to-text
and translation on the GPU machine beside the voice engines; the hosted services are the fallback when their keys
are set. Together 34.7 of 40 GB of GPU memory (SPEC section 21).

## Consequences

### Good

All **measured** 21 Nov, dense reel six loops, Tamil + Bengali, voice learned from the stream, hold 6 s, one run
each unless said (SPEC section 21):

| | Hosted (two runs) | All-GPU through the tunnel | All-GPU, backend on the GPU machine |
|---|---|---|---|
| First audio p50 / p95 | 2.8-2.9 s / 3.9-4.1 s | 2.3 s / 3.0 s | 1.8 s / 2.1 s |
| Within 0.25 s / 1 s / 2 s | 61-63% / 87% / 93-97% | 78% / 96% / 100% | 76% / 93% / 100% |

- Translation on the machine: 0.17 s (p95 0.29-0.41 s). No hosted one-request limit in the path.
- 67-minute real stream (21 Nov): end of phrase to text p50 0.69-0.72 s on the GPU engine against 0.77 s hosted.

### Bad

- Hard audio: key words right 70 clean / 49 hard of 80, against hosted 77 / 73 (SPEC section 21) -> ADR-0016.
- Source languages other than Hindi/Hinglish stay hosted; the source caption is Latin Hinglish.
- Model quirks found on a real stream: the noise word "nan" (9 of 1000 lines), dropped since (`f6d4c50`, `ff3a162`).
- Translation quality was read by eye on 42 lines, not scored; one error seen ("an hour and a half" became two
  hours in Punjabi).
- About 34.7 of 40 GB used: little room for new models (ADR-0026, ADR-0033).

## Evidence

- Experiments: [EXP-014](../experiments/EXP-014-standard-vs-gpu-engine.md), [EXP-015](../experiments/EXP-015-gemma-vs-gemini-latency.md),
  [EXP-016](../experiments/EXP-016-real-stream-67min.md)
- Commits: `cc7fd39` (all-GPU mode), `bcee6aa` (Studio), `4709425` (measured), `f6d4c50`, `ff3a162`, `be7540b`
- Sources: [`SPEC.md`](../../../SPEC.md) sections 20, 21; [`MODELS.md`](../../v1/MODELS.md); v0 `gpu_engine/README.md`
