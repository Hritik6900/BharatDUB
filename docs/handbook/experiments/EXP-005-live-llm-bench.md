# EXP-005: Live translation model bench (Gemini variants, wrong-script rate)

- **Date:** 2026-11-14
- **Status:** done
- **Decision:** ADR-0007 ([../adr/0007-hosted-llm-translation.md](../adr/0007-hosted-llm-translation.md))

## Question

Which hosted Gemini model translates a live phrase fastest without answering in the wrong script?

## Hypothesis

Not recorded; implied: a "lite" model is faster per phrase; the risk is replies that keep the Hindi (Devanagari) or
mix scripts.

## Setup

- Tool: `scripts/live_llm_bench.py`, 48 live phrases per model, the Live prompt, from the laptop.
- Models: `gemini-3.1-flash-lite`, `gemini-3.5-flash` (reasoning effort `none`), `gemini-3.5-flash-lite` (effort
  `minimal`; `none` is a 400 for lite), `gemini-3.7-flash`.
- Earlier the same week (2026-11-13), one-off timings of `gemini-3.5-flash` against `gemini-3.5-flash-lite` on live
  phrases.

## Metrics

- Time per phrase (mean or median not stated in the source; read as "per phrase").
- Wrong-script replies: replies with letters outside the target script and Latin (`wrong_script`), out of 48.

## Results

**measured**, 2026-11-14, 48 phrases per model (SPEC.md section 16; LIVE_TEST_REPORT.md item 5).

| Model | Time per phrase | Wrong-script replies |
|---|---|---|
| `gemini-3.1-flash-lite` | 0.82 s | 0 of 48 |
| `gemini-3.5-flash` | 1.02 s | 4 of 48 |
| `gemini-3.5-flash-lite` | 1.06 s | 4 of 48 |
| `gemini-3.7-flash` | 1.84 s | not given |

- 2026-11-13, one-off: `gemini-3.5-flash-lite` with `minimal` 0.8-0.95 s a phrase against 1.3-1.5 s for
  `gemini-3.5-flash`; lite sometimes returned the Hindi unchanged. **measured**, n not recorded.
- About 1 reply in 20 from the Flash models carried a word in the wrong script (Devanagari, once Georgian, inside a
  Tamil line). **measured**.
- Speed varies by hour: Gemini went from 0.8 s to 1.2-2.3 s a phrase in the afternoon of 2026-11-14. **measured**.

## Caveats

- One bench run per model; whether 0.82 s is a mean or a median is not stated.
- Translation quality was not scored, only speed and script.
- Spread (p95) not recorded.

## Decision taken

`LLM_MODEL_FAST=gemini-3.1-flash-lite` for Live; any reply with a wrong-script letter is redone once by the main model
(ADR-0007). This supersedes the 13 Nov flash-lite choice.

## Links

- [SPEC.md](../../../SPEC.md) section 16 (Live translation `LLM_MODEL_FAST`; "Live translation model is
  `gemini-3.1-flash-lite`")
- [LIVE_TEST_REPORT.md](../../../LIVE_TEST_REPORT.md) "What changed on 13 and 14 Nov", item 5
- Commits: `2188ad3` (faster translation model with fallback), `a88de86` (`gemini-3.1-flash-lite`, wrong-script redo,
  `live_llm_bench.py`)
- Related: [EXP-001](EXP-001-gnani-smoke-latency.md), [EXP-015](EXP-015-gemma-vs-gemini-latency.md)
