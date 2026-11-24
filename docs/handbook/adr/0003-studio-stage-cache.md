# ADR-0003: Studio stages cached by content hash; an edit re-runs one line

- **Status:** accepted
- **Date:** 2026-11-13
- **Superseded by:** —

## Context

Studio runs ten stages per job (`../../../SPEC.md` section 8). Speech-to-text, translation and voice are paid per
call; separation on the laptop CPU took 40.3 s for 60 s of audio (**measured**, 13 Nov, SPEC section 16, one run).
A creator fixing one translated line should not wait for, or pay for, the whole job again.

## Options considered

| Option | Status in the sources | Why it lost or won |
|---|---|---|
| Cache per stage, keyed by a hash of the input plus the stage's settings, shared across jobs | chosen; SPEC section 2, rule 3; section 18 | an unchanged rerun makes no paid call; one edited line re-runs stages 7-10 for that line only |
| No cache, rerun the job | not recorded (not evaluated) | every edit would pay speech-to-text again |
| Cache per job only | not recorded (not evaluated) | the same audio in a second job would be transcribed again |

## Decision

Content-addressed cache under `data/cache/<stage>/`, shared across jobs (SPEC section 18):

- separate: hash of `full.wav`;
- segment: vocals hash + parameters;
- transcribe: clip audio hash + language + model;
- translate: lines + language + glossary + model;
- voice: text + language + voice + model + sample rate.

"Never re-run STT unless audio changed" (SPEC section 2, rule 3). Edited lines are never overwritten by a
re-translation (SPEC section 18). The review editor sets `edited=true` and re-runs voice, fit, mix and render for
that line only (SPEC section 8).

## Consequences

### Good

- "A rerun of an unchanged job makes no paid call" (pitch PDF, 15 Nov, part A2).
- v1.1 WS3 scored old Studio HQ jobs again by a corrected rule without a new voice line, because what was heard is
  kept in the cache (`../../v1/PROGRESS.md`, phase 7 and v1.1 WS3).

### Bad

- A second run of the same video is served from the cache, so repeated Studio measurements need fresh input or a
  cleared cache. v1 phase 7 did only one run per path for that reason (`../../v1/PROGRESS.md`, phase 7, "Not done").
- A cache key that misses a setting serves stale output without a warning. v1's HQ flags were built so that with
  them off the cache keys stay the same (`../../v1/PROGRESS.md`, v1.1 WS3 intro); a full audit of the keys is not
  recorded.
- The cache grows without a limit; no eviction rule is recorded **(unconfirmed)**.

## Evidence

- Experiments: [EXP-021](../experiments/EXP-021-studio-hq-vs-standard.md),
  [EXP-027](../experiments/EXP-027-hq-judge-rerun.md)
- Commits: `df1fa91`/`f488544` (M2: Studio pipeline with cache)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 2, 8, 16, 18;
  [`PROGRESS.md`](../../v1/PROGRESS.md) phase 7, v1.1 WS3;
  [pitch PDF](../../../pitch/BharatDub_Architecture_Costs_Questions.pdf) (15 Nov, part A2)
