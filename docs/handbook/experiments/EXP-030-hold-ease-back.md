# EXP-030: The viewer hold after a slow link: stays up, or eases back

- **Date:** 2026-11-26
- **Status:** done (server side; the viewer page was not run in a browser)
- **Decision:** ADR-0035 ([../adr/0035-hold-ease-back.md](../adr/0035-hold-ease-back.md))

## Question

On the real 67-minute stream the hold grew from 6 s to 11 s while the link to the GPU machine stalled and stayed
there for the rest of the session ([EXP-016](EXP-016-real-stream-67min.md)). Can that be reproduced on the replay
harness, and does the new rule (`LIVE_SYNC_EASE`) bring the hold back to 6 s once the link is healthy, in small
steps, without making phrases late?

## Hypothesis

Written before the runs: with the rule off the hold ends where the slow spell left it; with it on, about 20 s
after the link is back the hold starts down in steps of 250 ms and reaches 6 s within a few minutes. Expected cost:
none on timing (a phrase must be ready 750 ms early before a step is taken).

## Setup

- Material: the dense 24.9 s Hindi reel replayed at real-time speed by `backend/eval/live_replay.py` (sync mode,
  video time every 0.5 s), 12 loops (312 s) or 16 loops (413 s); not a person at a microphone. Tamil, GPU engine,
  voice learned from the stream with consent.
- Two comparison backends on the laptop with the same code, `V1_ROUTER=true`, every other v1 flag off, the trace
  on: port 8120 with `LIVE_SYNC_EASE=false` ("off": the behaviour before this work) and port 8121 with the default
  ("on"). One session at a time; nobody was live on v0 or v1 (asked before every run).
- The link: one voice engine (9001), translation (9020) and our speech-to-text (9030) were reached through the
  local relay of [EXP-023](EXP-023-link-stalls-breaker.md), with one addition: a **slow** mode that passes every
  piece of data on 700 ms later in each direction (connections stay open). Slow from second 60 to second 130 of
  the feed, healthy before and after. This stands in for a link that stalls for a moment on every exchange, which
  is what the 67-minute stream had ("the machine answered in 2 ms and ping was fine meanwhile").
- A first attempt used the relay's hard stall (nothing passes; three stalls of 8 s at seconds 45, 75 and 105,
  rule off, 1 run). It did **not** move the hold: see "What the hard stall showed".
- Runs: off 2, on 2 (12 loops: off then on; 16 loops: on then off). The hold was read from
  `GET /api/live/sessions/<id>/metrics` once a second; per-phrase times from the comparison backend's own store.
- Rule settings (defaults): step 250 ms, at most one step in 5 s, 20 s without a late phrase before the first
  step, a phrase counts as in time when its sound was ready at least 750 ms before its moment.

## Metrics

- **Hold:** `sync_delay_ms`, how far a viewer's video is held behind the console's.
- **Within 0.25 s / 1 s:** share of spoken phrases whose dub starts that close to its video moment
  ([GLOSSARY](../GLOSSARY.md)), here for the phrases spoken after the link was back.
- **First audio:** end of a phrase's speech to its first dubbed sound.

## Results

All **measured**, 2026-11-26, one session per run.

| | Off, 312 s | Off, 413 s | On, 312 s | On, 413 s |
|---|---|---|---|---|
| Hold before the slow spell | 6.0 s | 6.0 s | 6.0-7.0 s (one step up at 40 s, one down at 60 s) | 6.0 s |
| Steps up during the slow spell (1 s each) | 5 | 5 | 4 (and the one before it) | 5 |
| Highest hold | 11.0 s | 11.0 s | 10.75 s | 11.0 s |
| First step down after the link was back | never | never | 22.3 s | 23.5 s |
| Steps down (largest) | 0 | 0 | 19 (250 ms) | 20 (250 ms) |
| Hold when the run ended | **11.0 s** (180 s after the link was back) | **11.0 s** (281 s after) | **6.25 s** (171 s after; the run ended one step short) | **6.0 s**, reached 217 s after the link was back and kept for the last 66 s |
| Steps up after the first step down | - | - | 0 | 0 |

Phrases spoken after the link was back (the hold is 11 s with the rule off, on its way to 6 s with it on):

| | Off, 312 s | Off, 413 s | On, 312 s | On, 413 s |
|---|---|---|---|---|
| Phrases timed | 82 | 127 | 84 | 133 |
| Within 0.25 s of the moment | 67.1% | 70.1% | 65.5% | 57.9% |
| Within 1 s | 97.6% | 95.3% | 96.4% | 95.5% |
| Latest start after its moment | 1.05 s | 1.61 s | 2.57 s | 2.50 s |
| Skipped as too late | 0 | 0 | 0 | 0 |
| First audio p50 / p95 | 2.18 / 3.34 s | 2.31 / 3.71 s | 2.20 / 3.42 s | 2.27 / 3.20 s |

For scale, the same sessions before the slow spell, hold 6 s in all four: within 0.25 s 57.7%, 61.5%, 60.0%,
53.8%; within 1 s 88.5%, 76.9%, 92.0%, 88.5% (25-26 phrases each). During the slow spell first audio p50 was
7.7-8.2 s and 25-48% of timed phrases started within 1 s.

Reading it:

- The bug is reproduced: a slow link of 70 s takes the hold from 6 s to 11 s, and with the rule off it is still
  11 s when the run ends, up to 281 s later.
- With the rule on the hold starts down 22-24 s after the link is back and comes down in steps of 250 ms; it
  paused three times in each run for about 30 s (a phrase without 750 ms in hand starts the 20 s wait again) and
  did not grow again. One run reached 6 s after 217 s; the other was at 6.25 s when its material ended.
- Within 1 s is the same with the rule on and off (95.5-96.4% against 95.3-97.6%). Within 0.25 s is lower with it
  on in both pairs (65.5% and 57.9% against 67.1% and 70.1%), and the latest start is later (2.5-2.6 s against
  1.1-1.6 s). Two runs each, and two equal runs differ by about 10 points, so this is not proven; it is what one
  would expect, since 11 s of hold leaves more room than 6 s. The figures with the rule on are in the range the same
  sessions had at 6 s before the slow spell (53.8-61.5%). The hypothesis "no cost on timing" is not confirmed for
  the 0.25 s figure.

## What the hard stall showed

Three stalls of 8 s with every v1 flag but the router off (1 run, rule off): the hold stayed at 6.0 s. 13 phrases
were skipped as too late and the ones that were spoken late were fewer than three in any six, which is what the
hold needs to grow. So a link that is simply dead for a few seconds loses phrases; it is a link that is slow for
a while that grows the hold. In that run no phrase was produced after second 194 of 312 fed, with no error
reported (the last three had captions and no sound). The slow-mode runs on the same backend ran to the end, so
this belongs to hard stalls without `V1_BREAKER` and `V1_LIVE_DEGRADE` (which exist for that case, EXP-023). It
was not looked into further.

## Caveats

- Two runs a setting on one reel in one language; the hold's path is the same in both pairs, the timing figures
  carry the usual spread.
- The slow link is made by a relay on the laptop, not by a real tunnel that stalls.
- **The viewer page was not run in a browser.** `/watch` now plays slightly faster (1.1x) after the hold came down
  until it has caught up; that is type-checked only. Whether a YouTube embed, and a live one, takes that speed is
  not known. A viewer whose player does not follow stays in step with its own picture and simply stays further
  behind live. The harness's viewers are sockets, not players.
- With `V1_BREAKER` + `V1_LIVE_DEGRADE` on, and with two or three languages, the rule was not measured.
- A speaker who pauses gives the rule fewer phrases to judge by; not measured.

## Decision taken

The rule is on by default with one switch, `LIVE_SYNC_EASE=false`, that restores the old behaviour (ADR-0035).

## Links

- [EXP-016](EXP-016-real-stream-67min.md) (where the hold stayed at 11 s), [EXP-011](EXP-011-sync-stamps-and-hold.md)
  (what a longer hold buys), [EXP-023](EXP-023-link-stalls-breaker.md) (the relay)
- Code: `backend/app/v1/hold.py`, `backend/app/live/pipeline.py` (`_note_late`, `_ease_hold`),
  `web/app/watch/[id]/page.tsx`; tests `backend/tests/test_v1_hold.py`
- Run data: `data-v1/eval/v12_hold/` on the build laptop (not in git)
