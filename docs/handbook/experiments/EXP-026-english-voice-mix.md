# EXP-026: English voice mix (WS2)

- **Date:** 2026-11-25
- **Status:** done
- **Decision:** ADR-0031 ([../adr/0031-english-single-voice.md](../adr/0031-english-single-voice.md))

## Question

In a GPU-engine session our voice engine has no English, so v0 chooses per line between the hosted copy of the
voice and a hosted stock voice. On the user's stream of 24 Nov that gave 100 English lines, 91 copied, 9 stock and
16 changes of voice. Should English be one voice for the whole session, and which one?

## Hypothesis

`V1_EN_SINGLE_VOICE` removes the changes of voice. `copy` (always the hosted copy) keeps the speaker's voice but
costs timing; `stock` keeps timing but is not the speaker's voice.

## Setup

- The dense 24.9 s reel played 8 times (211 s a session, about 95 phrases), GPU engine, English + Punjabi (English
  first, as on the user's stream), voice learned from the stream with consent, sync mode, hold fixed at 6 s.
- Three comparison backends in turn: flag off; on with `V1_EN_VOICE=copy`; on with `V1_EN_VOICE=stock`.
  **3 runs each**, 25 Nov 2026, about 00:40-01:15 IST. Tool: `eval/live_first.py`.
- The hosted stock voice was failing that night (HTTP 502 "technical difficulties" within 0.2 s): 5 of 18 single
  lines asked outside a session failed, and 59% of English stock lines failed at the first try in sessions
  ([INC-06](../INCIDENTS.md#inc-06-hosted-stock-voice-refusing-lines-http-502)).

## Metrics

English lines spoken, copied/stock share, stock lines between copied ones, changes of voice per session, lines
refused, lines asked twice, within 1 s of the moment, first audio p50/p95; the same from 120 s on (when the copy
existed in every run).

## Results

All **measured**, mean (lowest-highest) of 3 runs. Source: [PROGRESS.md "v1.1 WS2"](../../v1/PROGRESS.md).

| English lines | off | on, `copy` | on, `stock` (= `auto`) |
|---|---|---|---|
| Spoken, of about 95 | 69.7 (65-76) | 74.3 (73-76) | 54.7 (53-57) |
| Copied / stock, % of spoken | 59.7 / 40.3 | 67.3 / 32.7 | 0 / 100 |
| Stock lines between copied ones | 4.7 (3-6), 10.1% of lines from the first copied one on | 0 | 0 |
| Changes of voice in a session | 9 (7-11) | 1 (opening to copy) | 0 |
| Asked for and not made (refused) | 25.3 (21-30) | 20 (18-21), all before the copy existed | 39.3 (39-40) |
| Skipped as too late | 0 | 0 | 0 |
| Within 1 s of its moment | 90.9% (88.0-92.6) | 82.4% (79.5-88.0) | 90.6% (84.6-94.3) |
| First audio p50 / p95 | 2923 / 4184 ms | 2948 / 4298 ms | 2388 / 4100 ms |

From 120 s on (about 40 English lines a run):

| | off | on, `copy` | on, `stock` |
|---|---|---|---|
| Copied / stock, % of spoken | 90.3 / 9.7 | 100 / 0 | 0 / 100 |
| Refused, of about 40 | 3 (1-6) | 0 of 119 lines in three runs | 17.3 (15-22) after both tries |
| Within 1 s | 86.6% (76.9-92.1) | 73.7% (71.1-77.5) | 87.2% (77.3-96.2) |
| First audio p50 / p95 | 3191 / 4410 ms | 3085 / 4731 ms | 2353 / 3552 ms |

- A copied line's first audio is 0.73 s later than a stock line's (3.09 s against 2.35 s at the median).
- Every English line in the copy: within 1 s 86.6% -> 73.7% where the copy existed (lower in 2 of 3 pairs);
  backlog p95 862 -> 1359 ms; lines at 1.3x 13.7 -> 18.3 a run.
- Punjabi in the same sessions stayed at 92.8%, 91.4% and 89.9% within 1 s.
- The hosted copy learned from the stream said its first line 84-104 s after the first word in these six sessions
  (`SPEC.md` has 33-37 s on other material); likely cause not proven.
- The one retry brought back 16 of 55 refused lines a run in `stock` (29%).

## Caveats

- A night when the hosted stock voice was failing: the `stock` column spoke only 56% of its lines, so its queue was
  shorter and its timing is flattered. **The stock voice's timing on a healthy night was not measured.**
- 3 runs a setting; one reel; English + Punjabi only; nobody judged how either voice sounds.
- Not measured: a session with the hosted copy from its first line (a recorded voice), a real stream with pauses
  (24 Nov's stream had 97.9% of English lines within 1 s with 91% copied, EXP-022), the ladder with either setting
  on real services.

## Decision taken

`V1_EN_SINGLE_VOICE` built, default off; `auto` = the one stock voice, because always-copy measured clearly worse
on timing. `copy` is the setting for a night when the stock voice fails or when the speaker's voice matters more.
Which voice to use is the user's choice (ADR-0031, status proposed; approval checklist "which English voice").

## Links

- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "v1.1 WS2", "Measured: which voice says the English lines"
- [docs/v1/V1_1_SUMMARY.md](../../v1/V1_1_SUMMARY.md), section 2.4
- `logs/sessions/ws2-en-off/`, `ws2-en-copy/`, `ws2-en-stock/`
- Commit: `0ec4418`
- Related: [EXP-019](EXP-019-hosted-stock-vs-copied-voice.md), [EXP-022](EXP-022-real-streams-24nov.md),
  [EXP-025](EXP-025-session-warm-start.md)
