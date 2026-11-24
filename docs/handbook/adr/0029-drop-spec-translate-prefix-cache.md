# ADR-0029: Speculative translation and LLM prefix caching dropped (no measured gain)

- **Status:** accepted (removed in WS6)
- **Date:** 2026-11-25
- **Superseded by:** —

## Context

v1 phase 5 (23 Nov) built two latency ideas behind flags (`../../v1/PROGRESS.md` phase 5):

- `V1_SPEC_TRANSLATE` ("translation ahead"): start translating at a likely pause, before the final transcript.
- `V1_LLM_PREFIX_CACHE` ("fixed rules first"): reorder the translation prompt so the fixed rules come first,
  temperature 0.1, to get more prompt tokens from the server's prefix cache.

Both were measured in phase 5 on the dense reel, GPU engine, Tamil + Bengali, sync mode, hold 6 s, 3 runs each
(`../../v1/EVAL_REPORT.md` section 1.3).

## Options considered

| Option | Measured (23 Nov) | Outcome |
|---|---|---|
| Keep `V1_SPEC_TRANSLATE` | 4-6 early translations started a run, **0 used in 5 runs**; 3 of 4 were the speaker carrying on, 1 a final with fewer words than the partial. Partials arrive about 470 ms apart, so a pause is only certain after about 700 ms, when the final arrives anyway. Cost: 4-6 extra translation calls a language a minute | **removed** |
| Keep `V1_LLM_PREFIX_CACHE` | 61.4% of prompt tokens from the cache with it off and on (40 calls each); call p50 379 ms against 420 ms (noise). vLLM 0.34.0 on the shared server already had prefix caching on and already held each prompt | **removed** |
| Keep both off but in the code | rejected: dead code and trace fields with no use | — |

## Decision

v1.1 WS6 removed both flags with their code, tests, trace fields and the prefix-cache eval script (`e3128ef`). To
get them back: `bc48922` is the commit before (`../../v1/PROGRESS.md` v1.1 WS6). `same_words` stays (the HQ
transcript step uses it).

## Consequences

### Good

- Fewer flags and code paths (ADR-0020); 287 tests pass after removal (292 before; six tests of the removed code
  went, one new).
- Four to six translation calls a language a minute are not spent.

### Bad

- An env file that still sets a removed name is read without a warning (`Settings` uses `extra="ignore"`); tested.
- Old trace files in `logs/` still hold the removed fields; nothing reads them.
- The conclusion holds for this speech-to-text (partials every ~470 ms). With a recogniser that signals pauses
  earlier, speculation might pay; not measured.

## Evidence

- Experiments: [EXP-020](../experiments/EXP-020-v1-live-flags.md)
- Commits: `e2e9cca` (phase 5, flags added), `bc48922` (last commit with them), `e3128ef` (WS6, removed)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) phase 5 and v1.1 WS6; [`EVAL_REPORT.md`](../../v1/EVAL_REPORT.md) section 1.3;
  [`SUMMARY.md`](../../v1/SUMMARY.md) section 2
