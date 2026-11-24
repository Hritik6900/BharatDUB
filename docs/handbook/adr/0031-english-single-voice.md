# ADR-0031: English in a GPU session in one voice; `auto` = stock

- **Status:** proposed (user picks voice, item 22)
- **Date:** 2026-11-25
- **Superseded by:** —

## Context

IndicF5 has no English (`../../v1/MODELS.md`), so in a GPU-engine session English lines go to hosted voices
(ADR-0010): the hosted copy of the voice when there is time, a stock voice when there is not. On the user's
stream of 24 Nov: 100 English lines, 91 copied, 9 stock, 16 changes of voice (`../../v1/PROGRESS.md` v1.1 WS2,
read from v0's store). A viewer hears the voice switch back and forth.

## Options considered

English + Punjabi, reel played 8 times (211 s), GPU engine, learned voice, sync mode, hold 6 s, **3 runs each**
(**measured** 25 Nov, about 00:40-01:15 IST, `../../v1/PROGRESS.md` v1.1 WS2):

| English lines | Off (v0's mix) | On, `copy` | On, `stock` (= `auto`) |
|---|---|---|---|
| Copied / stock, % of spoken | 59.7 / 40.3 | 67.3 / 32.7 (stock only before the copy existed) | 0 / 100 |
| Changes of voice a session | 9 (7-11) | 1 | 0 |
| Within 1 s, from 120 s on | 86.6% | 73.7% | 87.2% (flattered, see below) |
| First audio p50, from 120 s on | 3191 ms | 3085 ms | 2353 ms |

- A copied line's first audio comes 0.73 s later than a stock line's (3.09 s against 2.35 s).
- That night the hosted stock voice refused many lines with HTTP 502 (59% at first try in sessions; 42% of English
  lines silent in `stock` even with one retry); the hosted copy answered 119 of 119. INC-06 in
  [`../INCIDENTS.md`](../INCIDENTS.md).

## Decision (proposed)

`V1_EN_SINGLE_VOICE` (default off) with `V1_EN_VOICE=auto|copy|stock`. `auto` takes the one stock voice, because
the brief for the work said that when always-copied makes timing clearly worse, the fixed stock voice is taken,
and it does. `copy` stays for whoever prefers the speaker's voice (one change, after the opening). The flag does
not switch by itself when the stock voice fails. Which voice is the user's decision (`../../v1/NEEDS_APPROVAL.md`
item 22).

## Consequences

### Good

- No mixed voices: 0 or 1 change a session instead of 9.
- Punjabi in the same sessions stayed 89.9-92.8% within 1 s: the English choice does not reach it.

### Bad

- `auto` means English is never in the speaker's voice.
- On a night like 25 Nov `auto` leaves lines silent; `copy` is the right setting then.
- The stock voice's timing on a healthy night was not measured; neither was how either voice sounds.
- The hosted copy learned from dense speech arrived 84-104 s into the session (SPEC had 33-37 s on other material).

## Evidence

- Experiments: [EXP-026](../experiments/EXP-026-english-voice-mix.md), [EXP-022](../experiments/EXP-022-real-streams-24nov.md)
- Commits: `0ec4418` (WS2)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) v1.1 WS2; [`V1_1_SUMMARY.md`](../../v1/V1_1_SUMMARY.md) section 2.4;
  [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) item 22
