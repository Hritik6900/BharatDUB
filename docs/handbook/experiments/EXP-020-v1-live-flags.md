# EXP-020: v1 phase 5 Live flags (dynamic phrase, merge, translate-ahead, late shorten, spec translate, prefix cache...)

- **Date:** 2026-11-23
- **Status:** done
- **Decision:** ADR-0029 ([../adr/0029-drop-spec-translate-prefix-cache.md](../adr/0029-drop-spec-translate-prefix-cache.md))

## Question

v1 phase 5 put eight Live changes behind flags (default off, ADR-0020). Does any of them move the two Live targets:
first audio p50 at most 1.8 s, and at least 90% of phrases on time?

## Hypothesis

- `V1_PHRASE_DYNAMIC` (short first phrase, longer later phrases, short-line merge): earlier first audio of a session.
- `V1_SPEC_TRANSLATE` (translate a phrase "ahead" from a stable partial before the final): saves a translation step.
- `V1_LLM_PREFIX_CACHE` (fixed prompt rules first, temperature 0.1): more prompt tokens served from the vLLM cache,
  faster translation.
- `V1_LIVE_LATE_SHORTEN`: fewer phrases skipped as too late.
- `LIVE_FIT_MAX_TEMPO=1.2` (cap 1.2x instead of 1.3x): not a speed change; a sound change.

## Setup

- Material: the dense 24.9 s Hindi reel, replayed at real-time speed (not a live person).
- GPU engine, Tamil + Bengali, sync mode, hold 6 s. Backend on the dev laptop, GPU servers through the SSH tunnel.
- Voice learned from the stream (three loops a run) and, separately, stock voices (two loops a run).
- Comparison backends started by `scripts/v1/ab-server.sh`, runs taken in turn, never two at once; `eval/v1/live.py`.
- **3 runs per setup**; mean and range reported. "v0" = v1 with every flag off (same providers, same pipeline code).
- Prefix cache: 40 translation calls with the flag off and 40 with it on, cache share read from the vLLM server.

## Metrics

First audio p50/p95 (end of phrase to first dubbed audio), within 0.25 s and within 1 s of the video moment,
phrases skipped as too late, phrases at the speed limit, first word of the session to first audio, translations
started ahead and used, share of prompt tokens served from the server's prefix cache, translation call p50.

## Results

All **measured**, 2026-11-23, source [PROGRESS.md "Phase 5"](../../v1/PROGRESS.md) and
[EVAL_REPORT.md section 1](../../v1/EVAL_REPORT.md).

Voice learned from the stream, mean (range) of 3 runs:

| | all flags off | `V1_PHRASE_DYNAMIC` | dynamic + ahead + prefix + late-shorten + 1.2x cap |
|---|---|---|---|
| First audio p50 | 2.34 s (2.27-2.40) | 2.37 s (2.28-2.41) | 2.46 s (2.42-2.50) |
| First audio p95 | 6.6 s (6.0-7.7) | 6.8 s (5.7-8.0) | 9.1 s (6.3-11.0) |
| Within 0.25 s | 69.6% (68.8-70.1) | 64.5% (62.7-66.0) | 56.0% (52.4-59.6) |
| Within 1 s | 83.3% (81.2-85.0) | 79.8% (78.9-81.4) | 75.6% (68.3-79.7) |
| Skipped as too late, a run | 4.7 (3-6) | 4 (1-6) | 1.7 (0-3) |
| At the speed limit, a run | 20 | 18 | 25.3 |
| First word of session to first audio | 7.2 s (6.4-8.0) | 7.2 s (6.3-7.8) | 7.6 s (6.4-8.7) |

Stock voices (voice ready at the first word), mean (range) of 3 runs:

| | all flags off | `V1_PHRASE_DYNAMIC` |
|---|---|---|
| First word of session to first audio | 5.9 s (4.9-6.5) | 4.1 s (4.0-4.4) |
| First audio p50 | 5.1 s (2.6-6.6) | 5.2 s (2.7-6.6) |
| Within 1 s | 58.3% (45.5-81.6) | 56.9% (43.5-81.6) |

Speculative translation and prefix cache:

| Flag | Result |
|---|---|
| `V1_SPEC_TRANSLATE` | **0 early translations used in 5 runs**; 4-6 started a run, all dropped. Three of four were the speaker carrying on; one was a final with fewer words than the partial. Partials arrive about 470 ms apart, so a pause is only certain after about 700 ms, when the final arrives anyway. Cost: 4-6 extra translation calls a language a minute. |
| `V1_LLM_PREFIX_CACHE` | **61.4% of prompt tokens from the server's cache with the flag off and with it on** (40 calls each); call p50 379 ms (off) against 420 ms (on), noise. The vLLM server (0.34.0) already had prefix caching on and already held the prompt for each word limit. |

Other flags: late-line shortening said 1-3 lines a run shorter (skips 4.7 -> 1.7 a run, inside a bundle whose
timing was worse); the 1.2x cap gave more phrases at the limit (25 against 20); back-check not measured (no scorer
without the QA server); stock default covered by a test only. The short-line merge was never exercised: 0 lines
joined (the reel has no one- or two-word lines).

## Caveats

- 3 runs per setup; v0's notes say two equal Live runs differ by about 10 points in timing.
- One dense reel, looped; no person at a microphone, no stream with short lines.
- Backend on the laptop: every phrase crosses the tunnel. v0 measured 1.8 s first audio with the backend on the GPU
  machine (21 Nov); that setup was not repeated here.
- Words heard back were not measured per run.
- The dynamic flag's gain (1.7 s earlier first audio) was measured with stock voices only, not with a streamer's
  recorded voice.

## Decision taken

- `V1_SPEC_TRANSLATE` and `V1_LLM_PREFIX_CACHE` were removed with their code in v1.1 WS6 (`e3128ef`, ADR-0029).
- `V1_PHRASE_DYNAMIC`: off by default; the user's call for sessions that start with a ready voice (it costs about
  5 points on time on dense speech).
- `V1_LIVE_LATE_SHORTEN`, `LIVE_FIT_MAX_TEMPO=1.2`, `V1_LIVE_BACKCHECK`: off.
- None of these flags moves first audio p50 to 1.8 s or on time to 90%. The measured lever for first audio is the
  backend on the GPU machine (`NEEDS_APPROVAL.md`).

## Links

- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "Phase 5" and "v1.1 WS6"
- [docs/v1/EVAL_REPORT.md](../../v1/EVAL_REPORT.md), sections 1.1-1.3
- [docs/v1/SUMMARY.md](../../v1/SUMMARY.md), section 2
- Commits: `e2e9cca` (phase 5), `8608b97` (phase 8 report), `e3128ef` (WS6 removal)
- Related: [EXP-024](EXP-024-dense-speech-budget.md), [ADR-0020](../adr/0020-flags-default-off.md),
  [ADR-0029](../adr/0029-drop-spec-translate-prefix-cache.md)
