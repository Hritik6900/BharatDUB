# EXP-004: First audio vs heard delay; trim, tempo fit, merge

- **Date:** 2026-11-14
- **Status:** done
- **Decision:** ADR-0008 ([../adr/0008-heard-delay-pacing.md](../adr/0008-heard-delay-pacing.md))

## Question

Phrase chunking cut first audio to 2.3 s (EXP-003). Does a viewer actually hear the dub sooner, and if not, what keeps
the dub from piling up in the player?

## Hypothesis

Not recorded; implied: the Tamil dub is longer than the Hindi speech, so audio queues in the player and the heard delay
grows; trimming silence, speeding up waiting phrases and merging queued phrases into one voice call should bring the
heard delay back down.

## Setup

- Data: the dense 24.9 s Hindi reel replayed at real time, 2 or 3 loops a run (`scripts/live_e2e.py`).
- Hosted path: Prisma realtime with partials, `gemini-3.1-flash-lite` for Live, Timbre stock voices (speed 1.15).
- Changes tested, each behind a switch: `LIVE_TRIM_SILENCE` (cut Timbre's silence, about 0.27 s a phrase),
  `LIVE_FIT` (ffmpeg `atempo` up to 1.3x when audio is still waiting), skip a phrase heard more than 8 s late,
  `LIVE_MERGE_MAX` = 3 (one voice call for up to 3 waiting phrases), `LIVE_TTS_ONLY_HEARD`.
- Per-language playhead `_playhead` gives a server estimate `t_heard:<lang>`; `scripts/live_player_sim.py` replays a
  run through the web player's rules.
- Backend on the laptop. One run per row.

## Metrics

- **First audio** and **heard delay** ([GLOSSARY](../GLOSSARY.md)): heard = end of a phrase to the moment the viewer
  starts hearing its dub, after earlier phrases have played. p50 / p95 / worst over the run.
- Skipped: phrases not spoken because they would be heard more than 8 s late.

## Results

All **measured**, 2026-11-14, one run per row (LIVE_TEST_REPORT.md "Results").

What a viewer got before and after (Tamil, one viewer):

| | 13 Nov evening (whole lines) | 14 Nov, phrases only | 14 Nov, final |
|---|---|---|---|
| Heard p50 / p95 | 3.4 s / 7.1 s (after a line of about 5 s) | 7.8 s / 11.1 s | 3.4 s / 5.8 s (after a phrase of about 1.2 s) |
| Skipped by the player | 0 of 10 | 1 of 25 | 0 of 26 |

Final settings, per run:

| Run | Viewers on | Phrases | First audio p50 / p95 | Heard p50 / p95 / worst | Skipped |
|---|---|---|---|---|---|
| 4 languages offered | Tamil | 26 | 2.7 s / 3.6 s | 3.4 s / 5.8 s / 5.9 s | 0 |
| 3 languages offered | Tamil | 26 | 3.5 s / 5.0 s | 4.4 s / 5.8 s / 6.2 s | 0 |
| (same run) | Bengali | 26 | 3.8 s / 4.7 s | 6.0 s / 7.5 s / 7.5 s | 0 |
| (same run) | English | 26 | 3.5 s / 4.9 s | 3.9 s / 5.5 s / 5.6 s | 0 |
| Voice learned from the stream, 4 offered | Tamil | 38 | 2.6 s / 3.5 s | 3.5 s / 6.7 s / 7.1 s | 3 |

- Cause found: the Tamil dub was 28% longer than the speech (64.4 s of audio for 50.3 s of talking). **measured**.
- `atempo` fit was applied to 21 of 26 phrases in the single-viewer run. **measured**.
- The server's heard estimate agreed with the player replay within 0.1 s on single-viewer runs. **measured**.
- In the learned-voice run 14 of 38 phrases were in the copied voice (hosted clone). **measured**.
- With `LIVE_BRIEF` (condensed translation while behind) the single-viewer run gave heard p50 3.4 s / p95 4.6 s
  (was 3.4 / 5.8 s); speed-ups 21 -> 12 phrases of about 26. **measured**, one run each.

## Caveats

- One run per row; a dense reel with no pauses is a hard case; no microphone, phone or session over 82 s.
- With three viewer languages the one-request account limit (EXP-001) is what separates the rows: Bengali heard 6 s.
- How a 1.3x speed-up sounds was not judged by ear.

## Decision taken

Live is judged by heard delay, not first audio. Trim, tempo fit (max 1.3x), skip after 8 s, merge up to 3 waiting
phrases, audio only for heard languages: all on by default, each with a switch (ADR-0008). Badges show heard delay.

## Links

- [LIVE_TEST_REPORT.md](../../../LIVE_TEST_REPORT.md) "Results", "What a viewer got before", "What changed"
- [SPEC.md](../../../SPEC.md) section 16 ("First audio is not what a viewer hears", `live_brief`)
- Commits: `a88de86` (trim, tempo fit, heard metric), `0b6d9f8` (merge waiting phrases), `d917086` (heard delay in
  the UI)
- Related: [EXP-003](EXP-003-live-stock-first-audio.md), [EXP-006](EXP-006-sync-mode.md)
