# ADR-0035: The viewer hold eases back to its normal value after it grew

- **Status:** accepted (on by default; kill switch `LIVE_SYNC_EASE=false`)
- **Date:** 2026-11-26
- **Superseded by:** —

## Context

In sync mode a viewer's video is held 6 s behind the console's so the dub is ready for its moment, and the hold
grows 1 s at a time when phrases keep arriving late ([ADR-0009](0009-sync-mode-hold.md)). It never came back: on
the 67-minute stream of 21 Nov it went from 6 s to 11 s during stalls of the link and stayed there
(`../../../SPEC.md` section 21; [EXP-016](../experiments/EXP-016-real-stream-67min.md)). The founder called this a
bug on 26 Nov 2026: after the link recovers the hold must ease back to 6 s smoothly. The older documents add that a
viewer's player leaves a small offset alone, so a lower number from the server does not by itself move a viewer who
is already watching.

## Options considered

| Option | What it is | Why it won or lost |
|---|---|---|
| Leave it | the hold only grows | the bug |
| Drop back to 6 s at once when the link is back | one jump of up to 9 s | rejected: every viewer's video would have to skip that much, and phrases already timed for the long hold would all be late at once (not measured) |
| Shrink on a timer | so many ms a minute whatever happens | rejected: it would shrink while phrases are still late |
| **Shrink a small step at a time, only on evidence that phrases have time in hand** | below | **chosen**; measured in EXP-030 |
| Tie it to the breaker's "link back" signal | start when the circuit closes | not chosen: the breaker is a flag that may be off, and lateness is what the hold is for whatever caused it |
| Viewer side: seek forward by each step | a jump in the picture every step | not chosen: a visible jump, and what a live embed does with small forward seeks is not known |
| Viewer side: play a little faster until caught up | 1.1x for a few seconds after each step | **chosen**, not verified in a browser |

## Decision

Server (`backend/app/v1/hold.py`, used by `LivePipeline._note_late`): with every spoken phrase the rule looks at how
long before its moment the phrase's sound was ready. The hold goes down one step (`live_sync_ease_step_ms`, 250)
when all of these hold: it is above the value the session began with; nothing was late for
`live_sync_ease_after_ms` (20 s), where "late" means ready less than step + `live_sync_ease_spare_ms` (500) before
its moment, or skipped as too late, or the hold just grew; at least three phrases were in time since then and one
since the last step; the last step is `live_sync_ease_every_ms` (5 s) old. It never goes under the session's
starting value (6 s; 8.5 s for a hosted copied voice) and never moves without phrases. A streamer's own YouTube
offset is not touched. Viewers get the new value with the next `sync` message; a session's metrics show
`sync_eased`, the trace `live_hold_eased`.

Viewer (`web/app/watch/[id]/page.tsx`): when a `sync` message carries a smaller hold than the one before, the page
asks its player for 1.1x until the video is within 0.05 s of where it should be, then for normal speed. Only then:
a player that is behind for another reason is left alone, as before. The clock that carries the video's time
forward and the timing of queued phrases use the speed the player reports.

One switch: `LIVE_SYNC_EASE` (default `true`). `false` = the hold only grows, and the viewer page never speeds up
(the server never sends a smaller hold).

## Consequences

### Good

- **Measured** (EXP-030, dense reel, Tamil, a link slowed for 70 s, 2 runs each): with the rule off the hold was
  11.0 s when the runs ended (180 s and 281 s after the link was back); with it on the first step down came 22.3 s
  and 23.5 s after the link was back, the largest step was 250 ms, the hold was 6.25 s when one run ended (171 s
  after) and 6.0 s from 217 s after in the other, and it did not grow again.
- Within 1 s after the link was back: 96.4% and 95.5% with the rule on, 97.6% and 95.3% with it off.
- Unit tests of the rule and of a session's hold through a stall (`backend/tests/test_v1_hold.py`).

### Bad

- Within 0.25 s after the link was back was lower with the rule on in both pairs (65.5% and 57.9% against 67.1%
  and 70.1%), and the latest start later (2.5-2.6 s against 1.1-1.6 s). Not proven at two runs each, but expected:
  a hold of 11 s leaves more room than 6 s. Easing gives that room back for 5 s less delay.
- **The viewer page is not verified in a browser** (no browser test exists in `web/`; type check only). If a
  player ignores the 1.1x, a viewer already watching stays further behind live than new viewers; the dub stays in
  step with their own picture either way. If the gap reaches 3 s the page's older rule seeks forward.
- On dense speech the way down pauses whenever one phrase lacks 750 ms in hand (three pauses of about 30 s in
  each measured run); a session that is always that tight never gets back to 6 s. That is the rule working, not a
  fault, but it means "back to 6 s" is not promised.
- Not measured: breaker and ladder on, several languages, a real tunnel, a speaker who pauses.

## Evidence

- Experiments: [EXP-030](../experiments/EXP-030-hold-ease-back.md); background
  [EXP-016](../experiments/EXP-016-real-stream-67min.md), [EXP-011](../experiments/EXP-011-sync-stamps-and-hold.md)
- Commits: see `../history/` (v1.2 Part 1)
- Sources: [`SPEC.md`](../../../SPEC.md) section 21 ("Open: the hold grew from 6 s to 11 s");
  [`PROGRESS.md`](../../v1/PROGRESS.md) "v1.2 Part 1"; [ADR-0009](0009-sync-mode-hold.md)
