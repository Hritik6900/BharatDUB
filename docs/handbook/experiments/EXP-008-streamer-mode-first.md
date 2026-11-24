# EXP-008: Streamer Mode first measurements (offset, on-time, voice build)

- **Date:** 2026-11-15
- **Status:** partial
- **Decision:** ADR-0012 ([../adr/0012-streamer-mode-recorded-voice.md](../adr/0012-streamer-mode-recorded-voice.md))

## Question

Can a streamer record their voice once (consent sentence read aloud), and have viewers hear them in that voice from the
first phrase, timed to the YouTube stream's delay?

## Hypothesis

Not recorded; implied: a stored, scored voice removes the ~9 s wait for a learned voice; a fixed offset equal to
YouTube's delay puts each phrase near its video moment. STREAMER_MODE.md set a target: 80% of phrases start within 1 s
of their video moment after calibration.

## Setup

- `/streamer`: profile, voice recorded with the consent sentence; the recording becomes a hosted embedding and a GPU
  voice: cleaned with Demucs on the GPU machine, up to three 7 s cuts, each transcribed from the exact cut and scored
  (a known sentence heard back by Prisma); best stored.
- Session: `streamer_id` + `voice_mode=clone`; stored voice sent to the IndicF5 engines at session start.
- Mic timing: each phrase due `offset_ms` after it was spoken; viewers report when each phrase started (`played`).
- Data: the dense 24.9 s Hindi reel fed as a microphone would. Backend on the laptop, GPU engines through the tunnel.
  One run per row.

## Metrics

- Voice build time (recording to a ready, tested voice) and score (share of the test sentence heard back).
- Phrases in the streamer's voice; **words heard back** ([GLOSSARY](../GLOSSARY.md)).
- **On time** in the viewer page: phrases started within 1 s of their moment; p95 lateness
  ([GLOSSARY](../GLOSSARY.md)).

## Results

All **measured**, 2026-11-15, one run each (SPEC.md section 16 "Streamer Mode"; README "Results").

| What | Result |
|---|---|
| Whole voice request | 17.6 s (11.7 s of it the GPU voice); score 1.0 on the first cut |
| Previews | 1.6-1.9 s |
| Tamil + Bengali, sync mode: phrases in the streamer's voice | 33 of 33 in each, from the first phrase |
| Hold | stayed 6 s |
| Words heard back | 87% Tamil / 80% Bengali |
| Edge viewer, offset 8 s: phrases arrived before due | 30 of 31 |
| Started within 1 s of the moment | 77%; p95 3.2 s late |

Live voice sample check (2026-11-15, same feature family): one run, score 0.89, and 86% of that run's dub words heard
back. **measured**, one run.

## Caveats

- The offset is set by ear; automatic calibration from the embed's sound was not built. The 80%-within-1 s target was
  for "after calibration", so it is not tested (status: partial).
- Not tested: a person at a real microphone, a real OBS to YouTube broadcast, a phone.
- The 20 Nov Streamer numbers (behind p50 0 s) were later found to come from a profile whose stored text was stale and
  whose lines came out twice too fast (SPEC section 20, 2026-11-21; see EXP-012, EXP-013).

## Decision taken

Streamer Mode ships with a recorded, scored, stored voice and a manual offset (ADR-0012). `live_clone_needs_streamer`
was first on, then switched off on 15 Nov by the founder's choice so `/live` can again copy a voice behind its consent
tick.

## Links

- [STREAMER_MODE.md](../../../STREAMER_MODE.md) sections 3, 5, 6
- [SPEC.md](../../../SPEC.md) section 16 ("Streamer Mode", "Live voice sample check")
- [README.md](../../../README.md) "Results", "Streamer mode, first measurements"
- Commits: `c401e5a` (phases 1-2 backend), `16b59a9` (phase 3 offset timing), `8d82653` (phases 4-5), `38e9b3c`
  (voice sample check), `89b68e4` (copy on `/live` again, switch off)
- Related: [EXP-012](EXP-012-clone-similarity.md), [ADR-0005](../adr/0005-consent-gates-cloning.md)
