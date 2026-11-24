# EXP-023: Link stalls of 24 Nov and the breaker/ladder test (WS0)

- **Date:** 2026-11-24
- **Status:** done
- **Decision:** ADR-0027 ([../adr/0027-breakers-degrade-ladder.md](../adr/0027-breakers-degrade-ladder.md))

## Question

1. What were the three moments on 24 Nov when every GPU service stopped answering at once (2 min, 3 h, 44 min)?
2. When the link to the GPU machine stalls, can a Live session keep dubbing (stock voice, hosted translation) and
   return to the copied voice by itself, instead of waiting on timeouts?

## Hypothesis

Per-endpoint circuit breakers plus a link-stall detector (`V1_BREAKER`) and a Live degrade ladder (copied voice,
stock voice, captions only, original sound; `V1_LIVE_DEGRADE`) keep every phrase translated and dubbed through a
stall, at a few seconds of extra first audio.

## Setup

- Part 1 (read-only): the stream watcher's `events.log` against the Windows event log.
- Part 2: the dense 24.9 s reel, six loops (about 160 s), Tamil, GPU engine, voice learned from the stream with
  consent, sync mode, comparison backends on 8111-8113 with `V1_ROUTER=true`. One voice engine (9001), translation
  (9020) and speech-to-text (9030) passed through a small relay on the laptop that can stop passing bytes
  (connections stay open and get nothing). One session at a time; nobody live on v0 or v1.
- Stall plans: all three GPU endpoints stalled for 50 s from second 43 (flags off: 1 run; flags on: 3 runs, two on
  an earlier build); GPU endpoints dead from the first second (flags on, 1 run); no hosted voice or translation,
  then the voice engine stalled at 38 s, everything at 78 s, all back at 113 s (flags on, 1 run of the final build).
- Breaker settings (chosen, not tuned): a timeout or 2 failures within 10 s opens an endpoint for 30 s; live
  translation on our model 3 s, a voice line 4 s; the detector asks every endpoint's health every 5 s (2 s limit).

## Metrics

During the stall: phrases translated, dubbed, translated by the hosted model; first audio median and worst. After:
time until the copied voice is back, share of phrases in the copied voice. Healthy calls against their limits.

## Results

All **measured**, 2026-11-24. Source: [PROGRESS.md "v1.1 WS0"](../../v1/PROGRESS.md).

Part 1: all three stalls were the laptop in Modern Standby, whose network is off: 15:05:53-15:07:46 against standby
15:05:18-15:07:04; 16:01:05-19:01:23 against standby from 16:01:00 and sleep until 19:00:51; 19:17:07-20:01:54
against standby 19:17:03-20:01:13 (local time). The hosted services were among the 8 that did not answer, which a
tunnel fault would not explain. See [INC-05](../INCIDENTS.md#inc-05-link-stalls-of-24-nov).

Part 2, 50 s stall of all GPU endpoints:

| During the stall | flags off (1 run) | breaker + ladder on (3 runs) |
|---|---|---|
| Phrases spoken by the speaker | 22 | 23, 24, 23 |
| Translated | 4 (18 went out in the source language) | 23, 24, 23 (all) |
| Dubbed | 4 | 23, 24, 23 (all, stock voice) |
| First audio after the phrase, median | 8.2 s (of the 4) | 3.5, 3.1, 3.4 s (before the stall 2.1, 2.2, 2.5 s) |
| First audio, worst | 8.7 s | 7.0, 7.0, 7.7 s |
| Translated by the hosted model | 0 | 23, 24, 23 |

- With the flags off a phrase waited for our translation model until the pipeline's own 8 s limit, so the hosted
  model was never reached. With them on the rung went to "stock" 3.1, 4.6 and 4.8 s after the stall began.
- After the link returned: earlier build 34.1 and 34.5 s until the copied voice was back (14 of 33 phrases still
  stock); final build (detector re-probes every 5 s) **5.6 s**, 33 of 33 phrases in the copied voice (1 run).
- GPU dead from the start (earlier build, 1 run): 75 of 75 phrases translated and dubbed (stock voice, hosted
  translation), first audio median 3.7 s / p95 5.8 s.
- Everything failing in turn (final build, 1 run): 67 phrases, a caption for each (1 in the source language), 21
  phrases during the stalls without audio, the copied voice back 8.5 s after everything returned; the session
  stayed live.
- Healthy calls through the relay over four runs: 169 voice lines, slowest 1.36 s (limit 4 s); 204 translation
  calls, slowest 1.13 s (limit 3 s).
- Found and fixed: a hosted voice whose connection drops raised an error the pipeline did not catch, so the ladder
  never heard of it; with the ladder on every voice error now counts.

## Caveats

- A local relay stands in for a stalled tunnel; the real tunnel was not touched.
- One reel, one language, stalls of 50 s at most; one to three runs per plan. The on/off difference is
  all-or-nothing; timing numbers carry the usual run-to-run spread.
- Not measured: Streamer Mode with a stored voice through a stall (fake engine only), two or three languages, the
  viewer page in a browser, the tunnel watchdog (written, not run), `/gpu` on the real card.
- A sleeping laptop also stops the backend: the breaker cannot help with the stalls of 24 Nov. The cure is power
  settings (`NEEDS_APPROVAL.md`).

## Decision taken

`V1_BREAKER` and `V1_LIVE_DEGRADE` stay behind their flags, default off; recommendation "on", the user's call
(ADR-0027). Stop the laptop sleeping on AC power (approval checklist).

## Links

- [docs/v1/PROGRESS.md](../../v1/PROGRESS.md), "v1.1 WS0"
- [docs/v1/V1_1_SUMMARY.md](../../v1/V1_1_SUMMARY.md), section 2.2
- [logs/streams/events.log](../../../logs/streams/events.log)
- Commit: `2cad302`
- Related: [EXP-016](EXP-016-real-stream-67min.md), [EXP-022](EXP-022-real-streams-24nov.md),
  [ADR-0011](../adr/0011-borrowed-a100-ssh-tunnels.md), [ADR-0019](../adr/0019-v1-on-laptop.md)
