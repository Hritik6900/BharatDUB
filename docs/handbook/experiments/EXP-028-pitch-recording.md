# EXP-028: Pitch kit recording chain check (WS4)

- **Date:** 2026-11-25
- **Status:** done
- **Decision:** ADR-0032 ([../adr/0032-opt-in-live-recording.md](../adr/0032-opt-in-live-recording.md))

## Question

Does the pitch chain work end to end: a Live session's dub kept on disk (`V1_LIVE_RECORD` plus a per-session ask),
then a side-by-side video (original beside dubbed, captions, numbers) rendered from that recording, with numbers on
the picture that match the backend's own trace?

This proves the chain. It is **not** a Live timing measurement: one run proves nothing about timing.

## Hypothesis

The numbers the renderer computes from the recording's `phrases.jsonl` equal the trace's numbers for the same
session, and the rendered file has the sound in the right ear at the right time.

## Setup

- 25 Nov 2026, 03:15 local, no other stream live on 8010 or 8110.
- Comparison backend on 8120 with `V1_LIVE_RECORD=true`, `V1_LIVE_BUDGET=true`, trace on, everything else off.
- The dense 24.9 s reel played 3 times with 0.4 s between and 6 s of silence first (84.8 s fed), Punjabi only,
  GPU engine, voice learned from the reel. Replay harness with `--record`.
- Renderer: `scripts/v1/render-pitch.ps1` (`backend/app/v1/pitch.py`, ffmpeg), stereo `split`.

## Metrics

Phrases and lines, recording size, first audio median, within 0.25 s / 1 s, copied-voice share, latest line,
rendered file properties; agreement between picture numbers and trace numbers.

## Results

All **measured**, 1 session. Source: [PROGRESS.md "v1.1 WS4"](../../v1/PROGRESS.md).

| | This session |
|---|---|
| Phrases, lines | 36 phrases in 35 voice calls (two in one call), none skipped |
| Recording | `dub_pa-IN.wav` 88.1 s, 4.2 MB; `phrases.jsonl` 35 rows |
| First audio, median | 2.3 s (picture: 2.275 s over 35 lines; trace: 2.331 s over 36 phrases) |
| Within 0.25 s / 1 s | 91.4% / 97.1% (picture and trace agree) |
| Copied voice | 33 of 35 lines (the first two stock, before the voice was learned) |
| Latest line | 4.1 s after its moment |
| Rendered video | 82.1 s, 35.3 MB, 812 x 720 (two panes of 406 x 720), 30 fps, H.264 + stereo AAC |

- Two frames were looked at (labels, numbers, a Gurmukhi caption with its letters joined, "this line +0.2 s"); the
  left channel is silent during the 6 s lead then carries the original; the right channel is silent until the
  first dubbed line at 7.75 s then carries the dub.
- Render time was not timed. The video stays in the data folder (over the 10 MB hook limit; video files ignored).

## Caveats

- One session, one language, one reel; a showcase of the chain, not of Live quality. Two equal runs differ by
  about 10 points.
- The picture says "on time" = within 0.25 s with "within 1 s" beside it, both labelled.
- Not measured: a recording from the console in a browser with a real YouTube video (tick and chip type-checked,
  not clicked); a microphone session through the renderer; more than one language on real material; a session
  longer than 88 s (the track is 2.9 MB a minute and language at 24 kHz); `dub` and `mix` stereo on real material;
  the blind listening page with real clips and listeners (no pairs exist).

## Decision taken

`V1_LIVE_RECORD` off by default and on only for a session whose speaker agreed to a video being made; recordings
are never deleted by themselves; viewers are not told a dub is being kept (only the dub is kept, no viewer data).
`V1_LISTEN_TEST` waits for pairs and listeners (ADR-0032).

## Links

- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "v1.1 WS4"
- [docs/v1/V1_1_SUMMARY.md](../../v1/V1_1_SUMMARY.md), section 2.7
- `logs/sessions/ws4-pitch/`, `logs/trace/ws4-pitch/`
- Commit: `bc48922`
- Related: [EXP-024](EXP-024-dense-speech-budget.md), [../PITCH_FACTS.md](../PITCH_FACTS.md)
