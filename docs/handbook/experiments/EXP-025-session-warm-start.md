# EXP-025: Session start warm start (WS2)

- **Date:** 2026-11-25
- **Status:** done
- **Decision:** none

## Question

Are the first phrases of a Live session slower than the rest because something is cold (connections, models,
the hosted voice)? Does a warm start (`V1_LIVE_WARMSTART`) bring the first 10 phrases' first audio down?

## Hypothesis

Warming every language and engine at session start (one tiny translation per language, every voice-engine
process asked for its state, a tiny hosted line per language, a streamer's stored voice sent when the session is
created), plus not holding opening lines for a voice that is not on its way, lowers first audio p95 of the first
10 phrases.

## Setup

- The dense 24.9 s reel played twice after 6 s of silence (about 26 phrases a session; the first 10 counted, each
  in two languages = 20 lines a run).
- GPU engine, Punjabi + Tamil, voice learned from the stream with consent, sync mode, hold fixed at 6 s.
- Two comparison backends in turn (off, on, off, on ...), **5 runs each way per build**, two builds (first build;
  final build that also stops opening lines waiting for a voice that is not coming). Night of 24-25 Nov 2026.
- Tool: `eval/live_first.py` over the replay folders.

## Metrics

For the first 10 phrases: first audio p50/p95, slowest line, lines in a stock voice / the copied voice / with no
audio, lines within 1 s of their moment. Also: warm-up call times, speaker pitch, which stock voice was picked.

## Results

All **measured**, mean (lowest-highest) over 5 runs. Source: [PROGRESS.md "v1.1 WS2"](../../v1/PROGRESS.md).

| First 10 phrases | off | first build | off (second batch) | final build |
|---|---|---|---|---|
| First audio p95 | 3859 ms (3556-4179) | 4793 ms (3851-5546) | 4268 ms (3673-5051) | 3798 ms (3396-4338) |
| First audio p50 | 2887 ms (2721-3080) | 2892 ms (2563-3105) | 2904 ms (2721-3108) | 2856 ms (2621-3368) |
| Slowest line | 4507 ms | 5170 ms | 4627 ms | 4285 ms |
| Lines in a stock voice, of 20 | 5.6 | 5.6 | 4.6 | 4.0 |
| Lines in the copied voice, of 20 | 13.8 | 14.4 | 14.2 | 13.6 |
| Lines with no audio, of 20 | 0.6 | 0 | 1.2 | 2.4 |
| Lines within 1 s of their moment, of 20 | 16.8 | 14.2 | 16.2 | 14.6 |

- First build: p95 **worse** (3.86 -> 4.79 s, 4 of 5 pairs); no cause found in the code path.
- Final build: p95 4.27 -> 3.80 s, lower in 4 of 5 pairs, ranges overlap. **Not a proven gain:** "off" alone moved
  0.41 s between the two batches, the size of the difference. The median did not move in either build.
- Nothing was cold: the hosted voice's warm-up line took 297-1428 ms (19 of 20 answered, mean 0.59 s); the first
  real stock line of an "off" session 0.77-1.13 s (Punjabi); a tiny translation 432-1104 ms and the first real one
  was no faster after it; asking the three engine processes 1.06-1.65 s. The opening is speech-to-text
  (0.85-0.93 s), translation (0.69-0.74 s) and, for stock lines, the hosted account's one request at a time shared
  by two languages (1.7-2.2 s from translation to first audio).
- First line in the copied voice 8.5-11.5 s after the first word, at phrase 4 or 5, in all 20 runs.
- Pitch: the reel's speaker measured 222 Hz in all ten runs (female), so the matched stock voices were the ones
  v0 uses anyway. The eight male stock voices each answered one two-word line (0.37-0.60 s).
- Lines with no audio are stock lines the hosted voice did not make; reason not recorded in these runs; the
  likely cause is the hosted voice refusing lines that night (INC-06), in both columns.

## Caveats

- Not measured: Streamer Mode with a stored voice (prefetch tested with a fake engine only), a male speaker, a
  session without the 6 s lead of silence, music or game sound under the voice, how the softened change of voice
  sounds, one viewer language, the hosted engine.
- 5 runs a side; batch-to-batch drift is as large as the effect.

## Decision taken

`V1_LIVE_WARMSTART` stays off (no proven gain). No ADR. The male stock voice and softened voice change need ears
and a male speaker (approval checklist item on what the session-start test could not cover).

## Links

- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "v1.1 WS2", "Measured: the first 10 phrases of a session"
- [docs/v1/V1_1_SUMMARY.md](../../v1/V1_1_SUMMARY.md), section 2.3
- `logs/sessions/ws2-off/`, `ws2-warm/`, `ws2-warm2/`
- Commit: `0ec4418`
- Related: [EXP-026](EXP-026-english-voice-mix.md), [INC-06](../INCIDENTS.md#inc-06-hosted-stock-voice-refusing-lines-http-502)
