# ADR-0037: Four features without a proven gain are removed with their flags

- **Status:** accepted (removed in v1.2 Part 2; what v1.2 Part 3 measured without them is below)
- **Date:** 2026-11-26
- **Superseded by:** —

## Context

Auto mode ([ADR-0036](0036-auto-mode.md)) ends the list of switches. The founder's decision of 26 Nov 2026 names
the features that go with their code rather than staying as switches nobody should use: `V1_SPEC_TRANSLATE` and
`V1_LLM_PREFIX_CACHE` (already removed in v1.1 WS6, [ADR-0029](0029-drop-spec-translate-prefix-cache.md)),
`V1_PHRASE_DYNAMIC`, `V1_LIVE_NATIVE_SPEED`, `V1_LIVE_WARMSTART`, and the manual `V1_LIVE_RATECTRL` flag ("the
controller lives only inside auto budget"). What their own measurements said (all quoted, none new):

| Feature | Measured | Source |
|---|---|---|
| `V1_PHRASE_DYNAMIC` | a session's first audio 5.9 s -> 4.1 s when a voice is ready at the start (stock voices); 5 points fewer phrases on time on dense speech (69.6% -> 64.5%, voice learned from the stream) | `../../v1/RUNBOOK.md` section 3 (v1.1 WS6); `../../v1/PROGRESS.md` Phase 5 |
| `V1_LIVE_NATIVE_SPEED` | acted on 6.6 lines a run, all Tamil; no timing number moved (5 runs each) | `../../v1/PROGRESS.md` v1.1 WS1 |
| `V1_LIVE_WARMSTART` | first audio p95 of the first 10 phrases 4.27 s -> 3.80 s with the final build and 3.86 s -> 4.79 s with the first, while "off" alone moved 0.41 s between batches: no proven gain; its matched stock voice and softened change of voice were never judged by ear | `../../v1/PROGRESS.md` v1.1 WS2 |
| `V1_LIVE_RATECTRL` (as a switch) | with the budget: 83.1% within 0.25 s against 80.6%, 91.8% within 1 s against 92.3%: inside the spread; it brought 1.4x on 15 lines a run, which nobody has heard | `../../v1/PROGRESS.md` v1.1 WS1 |

## Options considered

| Option | What it is | Why it won or lost |
|---|---|---|
| Keep them as overrides that can be pinned on | four more entries | rejected by the decision: dead features go with their code |
| Keep the code, drop the flags | unreachable code | rejected: code nobody can run is not tested by use |
| **Remove flag, code, tests, trace fields and their lines in the current-state documents** | below | **chosen** |
| Remove the controller too | | not asked: it stays, inside the auto budget only |

## Decision

Removed in v1.2 Part 2:

- `V1_PHRASE_DYNAMIC`: `DynamicPhraser`, the settings `V1_FIRST_PHRASE_*`, `V1_PHRASE_MIN_WORDS`,
  `V1_PHRASE_MAX_WORDS`, `V1_MERGE_UNDER_WORDS`. `ShortLineMerger` stays: dense speech in the auto budget joins a
  line of one or two words to the next one with it (`V1_DENSE_MERGE_UNDER_WORDS`, `V1_MERGE_WAIT_MS`).
- `V1_LIVE_NATIVE_SPEED`: the branch that asked our voice engine for part of a speed-up, `V1_NATIVE_MAX`,
  `V1_NATIVE_FLOOR_MS`, the `native` field of a phrase and of the trace, `native_speed` in the Live summary. (v0's
  own `GPU_VOICE_NATIVE_SPEEDUP` and Studio's engine speed are other things and stay.)
- `V1_LIVE_WARMSTART`: the warm-up for every language and engine, the stored voice sent when a session is created,
  the pitch tracker and the stock voice matched to the speaker, the softened change of voice, `V1_WARM_FADE_MS`,
  `V1_WARM_LEVEL_LINES`, the `open` and `handover` marks, the `warm` block of a session's metrics, the
  `live_warmstart` and `live_stock_voice` trace events. v0's own warm-up (`live_warmup`) is what runs.
- `V1_LIVE_RATECTRL` as a setting: the controller, dense mode's tighter budget and the joining of short lines run
  only when the auto budget is on. In manual mode `V1_LIVE_BUDGET` alone is v1.1's "budget" column.
- Their tests (in `test_v1_warm.py`, `test_v1_dense.py` and `test_v1_phrase.py`; the dense-mode and controller
  tests were written again for auto mode in `test_v1_auto.py`).

An env file that still sets any of these names is read and the names are ignored, in either mode: the backend
starts as if the lines were not there (`test_removed_flags_are_gone_and_an_env_file_that_still_sets_them_is_read`,
both modes). Reports of measurements stay as they were written; the trace files of earlier runs still hold the
removed fields and nothing reads them. `eval/live_first.py` still reads the `open` mark and the `warm` block of
old runs.

To get one back: the commit before this change is `339589c`
(`git show 339589c:backend/app/live/pipeline.py`, `app/v1/warm.py`, `app/v1/phrase.py`, `tests/test_v1_warm.py`).

## Measured after the removal (v1.2 Part 3, 26 Nov 2026)

Nothing was measured with the removed features (their code is gone); these are the numbers of what replaced them,
from [EXP-031](../experiments/EXP-031-auto-mode-dense-reel.md), 5 runs a setting on the dense reel.

- **Manual mode's `V1_LIVE_BUDGET` alone still gives v1.1's "budget" column:** 79.1% (73.2-81.8) within 0.25 s,
  90.0% (87.4-94.0) within 1 s, dur_ratio p90 1.16, first audio p50 2675 ms, against 80.6%, 92.3%, 1.17 and
  2627 ms on 24 Nov. The removal did not move the baseline.
- **The controller inside the auto budget, at 1.3x:** auto mode with the learned voice and no breaker (the setting
  nearest to v1.1's "budget + controller") had 74.2% (72.4-76.6) within 0.25 s, 88.5% (86.4-90.1) within 1 s and
  dur_ratio p90 1.16, against 83.1%, 91.8% and 1.11 for "budget + controller" at 1.4x on 24 Nov. Not the same
  thing (1.3x instead of 1.4x, the meaning check loosening the budget, another day), so not a like-for-like
  comparison; it is the nearest there is.
- **Lines at the 1.3x limit:** 27.6 a run with "budget on", 32.0-39.8 in the auto settings; none above 1.3x.
- **A voice ready at the first word did not give an earlier first sound** (the one gain `V1_PHRASE_DYNAMIC` had
  measured on stock voices): a session's first sound came 5.4 s (4.5-6.2) after its first phrase ended in pure auto
  (stock voices) against 5.3 s (5.0-5.7) with the learned voice in manual mode.

## Consequences

### Good

- Four fewer switches and nine fewer settings to explain, and no code that can only be reached by a switch
  nobody should use.
- The speed-up limit while speech is dense is back to 1.3x (`V1_DENSE_MAX_TEMPO`), so no viewer hears a speed that
  nobody has listened to.

### Bad

- The one gain measured for `V1_PHRASE_DYNAMIC` (a session's first audio 1.8 s earlier when a voice is ready at
  the start) is gone, and auto mode makes exactly that case the normal one for `/live` (stock voices from the
  first line). It was one measurement on stock voices; it was not repeated here.
- A male speaker gets the language's usual (female) stock voice again; the male voices are used only as the last
  voice of the fallback order ([ADR-0036](0036-auto-mode.md)).
- A streamer's stored voice is sent to the engines when the sound starts, not when the session is created.
- The "budget + controller" setting of v1.1 can no longer be started by a switch: in manual mode there is no
  controller, in auto mode it runs only while the budget is on. Its measured column cannot be repeated as it was.

## Evidence

- Experiments: [EXP-020](../experiments/EXP-020-v1-live-flags.md), [EXP-024](../experiments/EXP-024-dense-speech-budget.md),
  [EXP-025](../experiments/EXP-025-session-warm-start.md), [EXP-031](../experiments/EXP-031-auto-mode-dense-reel.md)
- Commits: see `../history/` (v1.2 Part 2); the last commit with the removed code: `339589c`
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) "v1.2 Part 2", v1.1 WS1, WS2, WS6, Phase 5;
  [`RUNBOOK.md`](../../v1/RUNBOOK.md) section 3; [ADR-0029](0029-drop-spec-translate-prefix-cache.md)
