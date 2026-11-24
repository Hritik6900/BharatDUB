# EXP-006: Sync mode: dub behind its video moment, hold

- **Date:** 2026-11-14
- **Status:** done
- **Decision:** ADR-0009 ([../adr/0009-sync-mode-hold.md](../adr/0009-sync-mode-hold.md))

## Question

Instead of hearing the dub a few seconds after the picture, can the viewer's video be held behind so each dubbed
phrase plays at the video moment it was spoken at? How long must the hold be, and how close does the dub land?

## Hypothesis

Not recorded; implied: a hold of about 6 s covers making the dub on most phrases; the hold has to grow when the APIs
are slow.

## Setup

- The `/live` console plays the session's YouTube video, captures its own tab and sends the player time on the ingest
  socket; each phrase carries `media_s`; `/watch` holds its player `delay_ms` behind (`LIVE_SYNC`,
  `LIVE_SYNC_DELAY_MS` start 6 s, 8.5 s with a copied voice; `LIVE_SYNC_ADAPT` grows it, limit 15 s).
- Data: the dense 24.9 s Hindi reel, three loops (82 s), Tamil, stock voice unless said, real hosted APIs, backend on
  the laptop. One run per row.
- Viewer page checked in Edge.

## Metrics

- **Behind** ([GLOSSARY](../GLOSSARY.md)): how long after its video moment a phrase started (0 = on it). p50 / p95 /
  worst.
- **Hold**: the delay viewers were held at by the end of the run.
- Skipped phrases.

## Results

All **measured**, 2026-11-14, one run per row (LIVE_TEST_REPORT.md "Sync mode").

| Run | Hold | Behind p50 / p95 / worst | Skipped |
|---|---|---|---|
| APIs fast | 8 s | 0.3 s / 1.9 s / 2.2 s | 1 of 39 |
| APIs slow (voice calls 2.5-4 s) | 10 s | 0.6 s / 2.8 s / 3.9 s | 0 of 38 |
| Voice learned from the stream (hosted clone), APIs slow | 14.5 s | 1.2 s / 2.6 s / 3.2 s | 0 of 38 |

- Edge viewer page: video held within 0.1-2.6 s of target (SPEC: 0.2-2.6 s); 15 of 18 phrases arrived before their
  moment. **measured**, one session.
- With the hosted clone only 5 of 21 spoken phrases were in the copied voice. **measured**.
- Same evening, `live_length_budget` (word limit for the translator from measured pace): phrases needing the 1.3x
  speed-up fell from 28-29 to 18-20 of about 30; with the natural-pace voice sample the reel was still about 1 s
  behind at the median (26 phrases, 4 skipped). **measured**, n of runs not recorded (SPEC section 16, 14 Nov night).

## Caveats

- Only uploaded videos, not a live YouTube broadcast; no phone; no person at a microphone.
- The two sources give the Edge video offset as 0.1-2.6 s and 0.2-2.6 s.
- What is behind is the dub's length on a speaker who never pauses, not its making time.

## Decision taken

Sync mode on with a 6 s start and adaptive growth (ADR-0009). The hold growth step was cut to 1 s on 2026-11-21
(EXP-011).

## Links

- [LIVE_TEST_REPORT.md](../../../LIVE_TEST_REPORT.md) "Sync mode: picture and dub together"
- [SPEC.md](../../../SPEC.md) section 16 ("Live sync mode"; "Copied voice cannot keep up"; "Live, 14 Nov night")
- Commits: `ecd2298` (sync mode, condensed translation, warm-up), `87d0c78` (word limit from measured pace)
- Related: [EXP-004](EXP-004-heard-vs-first-audio.md), [EXP-007](EXP-007-copied-voice-hosted-vs-gpu.md),
  [EXP-011](EXP-011-sync-stamps-and-hold.md)
