# ADR-0013: Startup product: best measured provider per capability, no single-vendor rule

- **Status:** accepted
- **Date:** 2026-11-21
- **Superseded by:** —

## Context

Bharat Dub began as an entry for two events: the Gnani AI challenge (submitted 13 Nov) and the Vihaan X hackathon
(14-15 Nov). The challenge shaped a preference for one vendor's speech and voice models. Both events were over by
21 Nov (`../../../SPEC.md` section 1). By then our own engine had already measured better than the hosted clone
for the Live copied voice (ADR-0010), and on 21 Nov the hosted speech-to-text failed every request for part of the
day (SPEC section 20; INC-02 in [`../INCIDENTS.md`](../INCIDENTS.md)).

## Options considered

| Option | Outcome |
|---|---|
| Stay with one vendor for speech-to-text and voice | rejected: single point of failure (21 Nov outage) and not the best measured voice for Live |
| Best measured provider per capability, behind the interfaces, with a fallback | **chosen** |
| Host every model ourselves | not chosen as a rule; done as an option per session (ADR-0014) |

## Decision

"No single-vendor rule. Each capability (speech-to-text, translation, voice) uses the provider that measures best,
behind the interfaces in section 7, with a fallback" (SPEC section 1, 21 Nov). The bar is "a stranger using it
without us in the room": reliability, cost per minute and behaviour when a provider is down count as much as the
best-case number. Every claim stays backed by a measured number.

State on 21 Nov (SPEC section 1): Gnani Prisma (speech-to-text), Gemini (translation), our IndicF5 on a GPU
(copied voice, Indian languages), Gnani Timbre (stock voices, English, fallback), Gnani Vachana (copied voice in
Studio, fallback in Live).

## Consequences

### Good

- Opened the all-GPU engine (ADR-0014, ADR-0015) the same day; speech-to-text gained a second provider, each the
  other's fallback for Hindi (SPEC section 21).
- Decisions are made by measurement: e.g. the hosted speech-to-text came back first in the GPU engine because it
  measured far better on hard audio (ADR-0016).

### Bad

- More providers to operate, monitor and pay; cost per dubbed minute is still not measured (SPEC section 20;
  `../../v1/NEEDS_APPROVAL.md` item 23: no prices set).
- Each new model brings its own licence question (ADR-0025, ADR-0026).
- Measurements vary by hour (hosted speed varies through the day, SPEC section 16), so "best" needs repeated runs.

## Evidence

- Experiments: [EXP-014](../experiments/EXP-014-standard-vs-gpu-engine.md), [EXP-018](../experiments/EXP-018-prisma-vs-whisper-hard-audio.md)
- Commits: `40f6183` (product direction, no single-vendor rule)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 1, 20, 21; [`README.md`](../../../README.md)
