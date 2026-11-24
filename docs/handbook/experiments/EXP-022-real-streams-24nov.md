# EXP-022: Real streams of 24 Nov (v0 and v1, from logs)

- **Date:** 2026-11-24
- **Status:** done
- **Decision:** ADR-0028 ([../adr/0028-dub-duration-budget.md](../adr/0028-dub-duration-budget.md))

## Question

How did Live behave on the user's own sessions on real videos on 24 Nov 2026, on v0 (port 8010) and v1 (port 8110),
read only from the logs? This is not a designed experiment: it is what the logs recorded.

## Hypothesis

None set beforehand. Read afterwards, the question became: does on-time fall when the speaker talks more of the time?

## Setup

- Source: `logs/sessions/index.csv`, rows with `date` 2026-11-24 and `version` v0 or v1 (one row per session and
  language); `logs/streams/v0_25239834.csv` (the stream watcher, a row every 20 s); `logs/streams/events.log`.
  Written by `scripts/v1/collect-logs.py` from the two stores. Aggregates only; no text, no video ids.
- Sessions started 08:10-09:30 UTC. Languages: Punjabi in every session; Tamil and English in some.
- v0: 13 sessions, 10 on the GPU engine and 3 on the hosted engine; v1: 4 sessions, all GPU engine. Voice learned
  from the stream in 15 of 17 sessions.
- Which v1 flags were on in those four v1 sessions is not recorded in the index **(unconfirmed)**.
- Whether outside viewers watched a real YouTube Live broadcast, or the user played real videos into the console,
  is not recorded **(unconfirmed)**. The documents call them "real videos" and "the user's stream".
- Backend on the laptop for both versions (no other setup existed).

## Metrics

Per session and language: phrases spoken, first audio p50/p95, within 0.25 s / 1 s of the video moment, copied-voice
share, speaking share of the speaker, lines at the speed limit, phrases skipped as too late. From the watcher:
viewer-reported on-time and the hold (`sync_delay_ms`).

## Results

All **measured** (computed from the logs on 2026-11-25; numbers in the index were written by the backends on
2026-11-24).

| | v0 | v1 |
|---|---|---|
| Sessions / session-languages | 13 / 21 | 4 / 6 |
| Minutes (sum of sessions) | 34.1 | 9.8 |
| Phrases spoken (all languages) | 692 | 203 |
| Punjabi first audio p50, median of sessions (range) | 2614 ms (1949-4558), n = 13 | 2111 ms (2107-2530), n = 4 |
| Punjabi within 0.25 s, median (range) | 57.9% (33.3-94.7) | 89.8% (71.8-92.1) |
| Punjabi within 1 s, median (range) | 76.5% (40.0-100.0) | 94.2% (76.9-100.0) |
| Within 1 s, all languages, weighted by phrases | 87.2% | 91.3% |
| Punjabi lines at the speed limit, median (range) | 25.0% (0-66.7) | 7.5% (4.3-19.5) |
| Punjabi speaking share, median (range) | 79% (48-86) | 70.5% (65-73) |
| Skipped as too late, total | 1 | 1 |

The longest session (v0, GPU engine, 16.4 min, 382 phrases, speaker talking 62% of the time):

| Language | Spoken | First audio p50 / p95 | Within 0.25 s / 1 s | Copied voice |
|---|---|---|---|---|
| Punjabi | 266 | 1949 / 3142 ms | 94.7% / 97.7% | 100% |
| English | 100 | 2735 / 4246 ms | 85.6% / 97.9% | 91.0% (9 stock lines, 16 changes of voice per [PROGRESS.md WS2](../../v1/PROGRESS.md)) |

Watcher at the end of that stream: viewer-reported on time 98.0% (300 reports), sync on time 92.0%, hold 6000 ms,
never grown.

The finding that started v1.1 WS1: a Punjabi session where the speaker talked 76% of the time (3.8 min, 80 phrases)
had 75.9% within 0.25 s and 84.8% within 1 s, against 94.7% / 97.7% in the 62% session; 16.2% of its lines were at
the 1.3x limit. [LIVE_DENSE_REPORT.md](../../v1/LIVE_DENSE_REPORT.md) summarises this as "fell from 95% to 76%" and
"the 1.3x limit was hit on 16-40% of lines".

Link: after these sessions, `events.log` shows every service unreachable three times (15:05-15:07, 16:01-19:01,
19:17-20:01 local time). These were the laptop in standby, not the tunnel (EXP-023,
[INC-05](../INCIDENTS.md#inc-05-link-stalls-of-24-nov)). No session in the index overlaps them.

## Caveats

- v0 and v1 sessions are different sessions on different material at different times; the table is not an A/B.
- Many sessions are short (0.6-4.4 min, except the 16.4 min one); a session-level median weighs a 1-minute session
  the same as a 16-minute one.
- Sessions with one or two lines in a language (Tamil rows) are in the counts; their 100% figures mean little.
- `index.csv` dates are UTC; the work log speaks in India time.
- No listener judged the dub; no words-heard-back on these sessions.

## Decision taken

The density finding led to the duration budget work (EXP-024, ADR-0028). The English voice mix (9 stock lines,
16 changes) fed EXP-026. The standby stalls led to EXP-023.

## Links

- [logs/README.md](../../../logs/README.md), [logs/sessions/index.csv](../../../logs/sessions/index.csv),
  [logs/streams/events.log](../../../logs/streams/events.log)
- [docs/v1/LIVE_DENSE_REPORT.md](../../v1/LIVE_DENSE_REPORT.md) (opening paragraph, section 4)
- Commit: `b2a091c` (logs folder, stream watcher, collect script)
- Related: [EXP-016](EXP-016-real-stream-67min.md), [EXP-023](EXP-023-link-stalls-breaker.md),
  [EXP-024](EXP-024-dense-speech-budget.md), [EXP-026](EXP-026-english-voice-mix.md)
