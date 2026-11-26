# ADR-0009: Viewer holds video (6 s start) and plays each phrase at its video moment; hold grows max 1 s a step

- **Status:** accepted
- **Date:** 2026-11-14
- **Superseded by:** —

## Context

Even with pacing (ADR-0008) the dub drifted against the picture: a viewer heard a phrase seconds after the
speaker's lips moved, by an amount that changed during the stream. The YouTube player on `/watch` and the dub had
no shared clock (`../../../SPEC.md` section 16, 14 Nov afternoon).

## Options considered

| Option | Outcome |
|---|---|
| Play the dub as it arrives (no sync) | kept as the behaviour when the viewer's video is not playing |
| Manual sync slider only (SPEC section 9, −5 s … +10 s) | kept, not enough alone |
| Sync mode: the console sends the player's time; each phrase is tagged with its video moment; the viewer holds its video behind | **chosen**, 14 Nov |
| Hold that grows by what the dub needs, 3 s steps (`live_sync_adapt`, limit 15 s) | used 14-21 Nov; one long line added 3 s for the rest of a session (21 Nov) |
| Fixed hold 6 / 7.5 / 9 s, growth off (21 Nov) | measured: the hold does not move the bulk, only the rare worst cases |

## Decision

- `/live` embeds the session's video, captures its own tab and sends `{"type":"media","t","playing"}`; phrases
  carry `media_s`; the server broadcasts `{"type":"sync","media_s","delay_ms"}`. `/watch` holds its player
  `delay_ms` behind the console's and starts each phrase at its moment.
- Hold starts at 6 s (8.5 s with a copied voice, 14 Nov), grows at most 1 s a step
  (`live_sync_grow_step_ms`=1000), and a phrase late in several languages counts once (21 Nov, `86188e5`).
- Stamps fixed (`live_stamp_fix`, 21 Nov): no phrase starts before the one before it ended; phrases share their
  line at an even pace.
- On a live YouTube stream the viewer pauses to wait instead of seeking back, which a live embed ignores (15 Nov).

## Consequences

### Good

- 14 Nov, stock voice, Tamil, 3 loops (**measured**, SPEC section 16): hold 8 s, dub behind its moment p50 0.3 s /
  p95 1.9 s, 1 of 39 skipped (fast hour); hold 10 s, 0.6 s / 2.8 s (slow hour).
- 21 Nov, hold fixed, six loops, about 140 phrases over Tamil + Bengali (**measured**, SPEC section 20):
  6 s: 64% within 0.25 s, 91% within 1 s; 7.5 s: 71% / 90%; 9 s: 62% / 90%.

### Bad

- The viewer watches 6 s or more behind the stream.
- The hold never comes back down: on the 67-minute stream it grew from 6 s to 11 s during link stalls (21 Nov,
  SPEC section 21). Lowering it needs a viewer-page change and a browser test (open).
  **Since 26 Nov 2026** the hold eases back ([ADR-0035](0035-hold-ease-back.md)); the browser test is still open.
- Only works with the console's own tab as the sound source; mic and other-tab sessions are unchanged.
- Not measured on 14 Nov: a live YouTube broadcast, a phone, a person at a microphone.

## Evidence

- Experiments: [EXP-006](../experiments/EXP-006-sync-mode.md), [EXP-011](../experiments/EXP-011-sync-stamps-and-hold.md),
  [EXP-016](../experiments/EXP-016-real-stream-67min.md)
- Commits: `ecd2298`/`65bd642` (sync mode), `71ca7cc`/`b478629` (pause instead of seek), `a60b6d8` and `6667f1a`
  (stamp fix), `86188e5` (grow 1 s a step)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 9, 16, 20, 21
