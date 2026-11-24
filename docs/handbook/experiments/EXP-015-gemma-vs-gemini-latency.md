# EXP-015: Gemma 4 E4B on own GPU vs hosted Gemini: translation latency

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** ADR-0015 ([../adr/0015-gpu-stt-translation.md](../adr/0015-gpu-stt-translation.md))

## Question

How much translation time per live phrase does an open model on our own GPU (Gemma 4 E4B on vLLM) save against hosted
Gemini, and does it keep the target script the voice engine needs?

## Hypothesis

Not recorded; implied: a 4 B-class model next to the voice engines answers several times faster than a hosted call,
because the network trip is gone.

## Setup

- GPU: `google/gemma-4-E4B-it`, bf16, vLLM on port 9020, about 19 GB (`LLM_GPU_SHARE` 0.5), on the A100 GPU VM
  (address in `docs/v1/NEEDS_APPROVAL.md`); own short prompt (`providers/llm_local.py`).
- Hosted: `gemini-3.1-flash-lite` (the Live default of the time; that this model served the site check is (unconfirmed)) through the OpenAI-compatible endpoint (Live hosted path; EXP-005).
- Placements: (a) backend on the GPU machine; (b) backend on the laptop, model through the SSH tunnel (the real site).
- Data: the dense 24.9 s Hindi reel; for (b) one Live session each way on the site.

## Metrics

- Translation time per phrase: p50 (and p95 where given), as recorded per phrase by the Live pipeline.
- Translation to first audio (GPU machine placement).
- Lines with English words left in Latin letters (which the voice engine cannot read).

## Results

All **measured**, 2026-11-21. The numbers come from different conditions; they are not one controlled A/B.

| Condition | Hosted Gemini | Gemma 4 E4B on our GPU | Source |
|---|---|---|---|
| "Where the time went", one line of the reel | 0.85-0.95 s | - | SPEC section 21 |
| Backend on the GPU machine (a Live run of the reel (unconfirmed)) | - | 0.17 s (read as p50 (unconfirmed); p95 0.29-0.41 s); translation to first audio 0.62 s | SPEC section 21 |
| Real site, backend on the laptop, one session each way | 0.96 s p50 (session of 35 source lines; n of translated phrases (unconfirmed)) | 0.55 s p50 (session of 42 source lines; n (unconfirmed)) | SPEC section 21 intro |
| Earlier bench, 48 phrases (14 Nov) | 0.82 s (`gemini-3.1-flash-lite`) | - | EXP-005 |

Script, **measured**: on the hosted Live prompt the small model left English words in Latin letters in 7-10 of 14
lines; on its own prompt 0 of 42. Sample text rewrite into Devanagari by the model: 0.7 s once per sample.

## Caveats

- The 0.55 s through the tunnel includes the tunnel trip; the 0.17 s on the machine does not. Neither is a
  same-session A/B with the hosted figure.
- The 0.96 s hosted p50 and 0.55 s GPU p50 come from the site check whose aim was to prove the Engine button switches
  providers (one session each, SPEC section 21 intro), not a latency benchmark.
- Quality: read by eye on 42 lines, not scored; one error seen (an hour and a half became two hours in
  Punjabi).
- Whether vLLM prefix caching was on in these runs is (unconfirmed); v1 later read 52.8% cached prompt tokens on the
  same server (docs/v1/EVAL_REPORT.md section 4, 23 Nov).
- Gemma 3 models and SraVaani were gated on Hugging Face and not tried.

## Decision taken

The GPU engine translates with Gemma 4 E4B on vLLM, hosted Gemini as fallback (ADR-0015). The hosted engine keeps
Gemini.

## Links

- [SPEC.md](../../../SPEC.md) section 21 (intro "Checked on the site"; "Where the time went"; "Found on the way" (2))
- [gpu_engine/README.md](../../../gpu_engine/README.md) "All-GPU mode" (models, prompt note)
- Commits: `cc7fd39` (all-GPU mode), `4709425` (measured and documented), `31673b9` (engine per session; site check)
- Related: [EXP-005](EXP-005-live-llm-bench.md), [EXP-014](EXP-014-standard-vs-gpu-engine.md),
  [ADR-0007](../adr/0007-hosted-llm-translation.md)
