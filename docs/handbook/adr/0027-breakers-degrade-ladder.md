# ADR-0027: Circuit breakers + Live degrade ladder (copied voice, stock, captions, original)

- **Status:** accepted (flag; recommendation: on, user's call)
- **Date:** 2026-11-24
- **Superseded by:** —

## Context

On 24 Nov every GPU service was unreachable at once three times (2 min, 44 min, 3 h) (`../../v1/PROGRESS.md`,
v1.1 WS0). All three turned out to be the laptop in Modern Standby (INC-05), but an awake PC also has stalls: a
dead tunnel, a stuck ssh, a server down on the GPU machine. On the 67-minute stream of 21 Nov every bad stretch
sat on a link stall (`../../../SPEC.md` section 21). With the old code a phrase waited for our translation model
until the pipeline's own 8 s limit, so the hosted fallback was never reached.

## Options considered

| Option | Outcome |
|---|---|
| v0's per-call timeouts and fallbacks only | measured below: 4 of 22 phrases dubbed through a 50 s stall |
| Breaker inside `V1_ROUTER` | rejected: it is attached where a GPU provider object is built, in the router and in v0's table alike, so it works with the router on or off |
| Breakers per GPU endpoint + link-stall detector (`V1_BREAKER`) + Live ladder (`V1_LIVE_DEGRADE`) | **chosen**, both default off |
| Fix the cause (stop the laptop sleeping) | also needed: three `powercfg` lines (`../../v1/NEEDS_APPROVAL.md` item 16) |

## Decision

- One breaker per GPU endpoint: a timeout, or 2 failures in 10 s, opens it for 30 s; calls fail at once and the
  existing fallback answers. Client errors (4xx) do not count. Live call limits: 3 s translation, 4 s a voice line.
- `LinkWatch`: every GPU endpoint's health asked every 5 s (2 s limit); all failing in one round = the link: every
  circuit opens at once; the probe is also the half-open try.
- Ladder: copied voice -> stock voice -> captions only -> original sound. Two failures step down, one success steps
  up. Viewers see a short note; the rung is in `clock`, `degrade`, metrics and the trace.

## Consequences

### Good

Relay-made 50 s stall of all GPU endpoints, dense reel, Tamil (**measured** 24 Nov, `../../v1/PROGRESS.md` v1.1 WS0):

| During the stall | Flags off (1 run) | Breaker + ladder (3 runs) |
|---|---|---|
| Phrases dubbed | 4 of 22 | 23, 24, 23 (all, stock voice) |
| First audio, median | 8.2 s | 3.5, 3.1, 3.4 s |

Copied voice back 5.6 s after the link returned (final build, 1 run). No healthy call came near its limit
(slowest voice line 1.36 s, slowest translation 1.13 s).

### Bad

- A stock voice is not the speaker's voice; the hosted services must be reachable for the rungs to help.
- Not measured: a real stalled tunnel (a relay stood in), stalls over 50 s, several languages, Streamer Mode
  through a stall, the viewer page in a browser.
- Off by default: the user decides (`../../v1/SUMMARY.md` section 2, "your call").

## Evidence

- Experiments: [EXP-023](../experiments/EXP-023-link-stalls-breaker.md), [EXP-016](../experiments/EXP-016-real-stream-67min.md)
- Commits: `2cad302` (WS0)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) v1.1 WS0; [`V1_1_SUMMARY.md`](../../v1/V1_1_SUMMARY.md) section 2.2;
  [INC-05](../INCIDENTS.md#inc-05-link-stalls-of-24-nov)
