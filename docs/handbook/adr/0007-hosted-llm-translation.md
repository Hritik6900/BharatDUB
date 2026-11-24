# ADR-0007: Hosted Gemini translation via OpenAI-compatible endpoint; flash-lite model for Live; wrong-script redo

- **Status:** accepted (Live hosted path)
- **Date:** 2026-11-13
- **Superseded by:** — (complemented by [ADR-0015](0015-gpu-stt-translation.md): the GPU engine translates with Gemma 4 E4B first, Gemini behind it)

## Context

The spec planned a hosted Gnani LLM ("Evon"). On 13 Nov the Gnani dashboard listed only speech-to-text and voice,
no LLM endpoint (`../../../SPEC.md` section 16). Translation had to come from somewhere else, in natural spoken
style and in native script.

## Options considered

All measured on the real APIs (SPEC section 16):

| Option | Measured | Outcome |
|---|---|---|
| Gnani-hosted LLM | not available on the dashboard (13 Nov) | not possible |
| `gemini-3.5-flash`, thinking on | 4-5 s and truncated replies (13 Nov) | rejected |
| `gemini-3.5-flash`, `LLM_REASONING_EFFORT=none` | 1.4-2.2 s for a 3-line batch, ~1.5 s a live chunk (13 Nov) | **Studio model** |
| `gemini-3.5-flash-lite` for Live, `minimal` effort | 0.8-0.95 s a phrase against 1.3-1.5 s (13 Nov); sometimes returned the Hindi unchanged | used 13-14 Nov, then replaced |
| Live bench, 48 replies each (14 Nov, `scripts/live_llm_bench.py`) | `gemini-3.1-flash-lite` 0.82 s, 0 of 48 wrong script; `3.5-flash` 1.02 s, 4 of 48; `3.5-flash-lite` 1.06 s, 4 of 48; `3.7-flash` 1.84 s | **`gemini-3.1-flash-lite` for Live** |

## Decision

- Translation through an OpenAI-compatible endpoint (`LLM_BASE_URL`, today Gemini), provider `llm_openai.py`.
- `LLM_MODEL` for Studio, `LLM_MODEL_FAST=gemini-3.1-flash-lite` for Live, reasoning effort per model.
- Prompts demand native script (models answered Hinglish input in romanised Tamil otherwise).
- `wrong_script`: any reply with letters outside the target script and Latin is redone once by the main model.

## Consequences

### Good

- Live translation under 1 s a phrase on a good hour (0.82 s, 14 Nov bench).
- No model to host; the provider can be swapped by settings (ADR-0013).

### Bad

- Speed varies through the day: 0.8 s to 1.2-2.3 s a phrase in the same hours (**measured** 14 Nov, SPEC section 16).
- The hosted Live prompt on the small model left English words in Latin letters in 7-10 of 14 lines, while
  Gemma's own prompt did so in 0 of 42 (21 Nov, SPEC section 21).
- One more external dependency per phrase; a hosted outage stops translation unless the GPU engine is chosen.
- Cost per minute not measured (SPEC section 20).

## Evidence

- Experiments: [EXP-005](../experiments/EXP-005-live-llm-bench.md), [EXP-015](../experiments/EXP-015-gemma-vs-gemini-latency.md)
- Commits: `ee932e8`/`5f43e78` (Gemini, reasoning effort, native-script prompts), `2188ad3`/`4c3bc2b` (faster
  model with fallback), `a88de86`/`de4a631` (`wrong_script` redo), `d917086`/`70544cf` (`gemini-3.1-flash-lite`)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 4, 7, 16, 21
