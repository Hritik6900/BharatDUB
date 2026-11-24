# ADR-0012: Streamer Mode: voice recorded once with spoken consent, scored, stored

- **Status:** accepted
- **Date:** 2026-11-15
- **Superseded by:** —

## Context

A voice learned from the stream is not there at the start: hosted clone ready 33-37 s into the stream (13 Nov),
GPU voice about 9 s (14 Nov) (`../../../SPEC.md` section 16). Until then viewers hear a stock voice. A streamer who
goes live every day should sound like themselves from the first sentence. A sample's quality decides the dub's
quality: the engine copies pace and words from it (SPEC section 16).

## Options considered

| Option | Outcome |
|---|---|
| Learn the voice from each stream (Live, with consent tick) | kept on `/live`; late start, sample quality varies |
| Record once, store, reuse (Streamer Mode) | **chosen** 15 Nov |
| Hosted embedding only | stored beside the GPU voice for Studio, English and as a backup |

## Decision

`/streamer` (spec in `../../../STREAMER_MODE.md`):

- A streamer profile; the voice recorded once in the browser with the consent sentence read aloud (ADR-0005).
- The recording is cleaned with Demucs on the GPU machine, up to three 7 s cuts are made, each transcribed from the
  exact cut and scored (the voice says a known sentence, Prisma hears it back); the best is stored (`ref_path`,
  `ref_text`, `ref_score`) plus a hosted embedding.
- A session with `streamer_id` + `voice_mode=clone` sends the stored voice to the engines when it starts.
- Mic sessions: each phrase is due `offset_ms` after it was spoken (YouTube's delay), console slider 0-40 s.

## Consequences

### Good

- Voice build: 17.6 s for the whole request (11.7 s for the GPU voice), score 1.0 on the first cut, previews
  1.6-1.9 s (**measured** 15 Nov, SPEC section 16).
- Tamil + Bengali, sync mode: 33 of 33 spoken phrases in the streamer's voice in each language, from the first
  phrase; hold stayed 6 s; 87% / 80% of words heard back (**measured** 15 Nov).
- Mic timing, offset 8 s, Edge, dense reel: 30 of 31 phrases arrived before they were due; 77% started within 1 s
  of their moment, p95 3.2 s late (**measured** 15 Nov).

### Bad

- A recorded voice speaks at the pace of its sample; on the dense reel recorded voices were late whatever the
  steps: 56-57% within 1 s (21 Nov, SPEC section 20). Not measured: a streamer at their own normal pace.
- A stored profile's text went stale once (INC-03, ADR-0004); `voice_ref.sample_text` now checks text length
  against the file.
- The offset is set by ear; automatic calibration was not built.
- Not tested: a real microphone with a person, a real OBS -> YouTube broadcast, a phone (SPEC section 16).

## Evidence

- Experiments: [EXP-008](../experiments/EXP-008-streamer-mode-first.md), [EXP-012](../experiments/EXP-012-clone-similarity.md),
  [EXP-013](../experiments/EXP-013-steps-and-pace.md)
- Commits: `c401e5a`/`b8fcda3` (backend), `e2056c1`/`e6d3322` (web), `16b59a9`/`5b9958f` (mic timing and
  offset), `8d82653`/`f3dc17d` (phases 4-5), `86188e5` (sample text check)
- Sources: [`STREAMER_MODE.md`](../../../STREAMER_MODE.md); [`SPEC.md`](../../../SPEC.md) sections 16, 20;
  [pitch PDF](../../../pitch/BharatDub_Architecture_Costs_Questions.pdf) (15 Nov, part A4)
