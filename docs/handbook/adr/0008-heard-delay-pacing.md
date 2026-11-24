# ADR-0008: Judge Live by what the viewer hears: playhead, trim, tempo fit (max 1.3x), skip >8 s late, merge waiting phrases, audio only for languages with viewers

- **Status:** accepted
- **Date:** 2026-11-13
- **Superseded by:** — (the length of the dub is now also planned before translation: [ADR-0028](0028-dub-duration-budget.md))

## Context

Phrase chunking (ADR-0006) cut "first audio" to 2.3 s. But first audio is not what a viewer hears. The Tamil dub
came out 28% longer than the speech (64.4 s for 50.3 s), so audio piled up in the player: **heard** p50 7.8 s
(**measured**, 14 Nov, `../../../SPEC.md` section 16, dense reel). Also, with one hosted request at a time, making
audio for languages nobody listens to wasted the only slot (SPEC section 9, concurrency caveat).

## Options considered

| Option | Outcome |
|---|---|
| Keep measuring first audio only | rejected: it hid a 7.8 s heard delay |
| Let the player speed up (1.1x when more than 2 s is waiting, skip a chunk more than 10 s late) | kept in the viewer (13 Nov), not enough alone |
| Server-side pacing per language (chosen) | below |
| A shorter translation while behind (`live_brief`, 14 Nov) | added |
| Planning the dub's length before translating | came later as ADR-0028 (24 Nov) |

## Decision

- Audio only for languages a viewer is tuned to (`live_tts_only_heard`, 13 Nov); captions always go out.
- A per-language playhead (`_playhead`: when a viewer's queued dub ends); `t_heard:<lang>` stored per chunk; stats
  and badges show `heard_p50_ms` / `heard_p95_ms`.
- Trim the voice's silence around each phrase (`live_trim_silence`); speed up with ffmpeg `atempo` up to 1.3x when
  audio is waiting (`live_fit*`); skip a phrase heard more than 8 s late (`live_skip_after_ms`; 4 s in sync mode,
  `LIVE_DENSE_REPORT.md` section 2); speak up to 3 waiting phrases in one voice call (`live_merge_max`).
- `live_brief`: while a language is 0.5 s behind, ask for a condensed translation.

## Consequences

### Good

- Heard delay, same reel (14 Nov, **measured**, SPEC section 16): 1 viewer language p50 3.4 s / p95 5.8 s;
  3 viewer languages 3.9-6.0 s / 5.5-7.5 s; learned voice 3.5 s / 6.7 s. `scripts/live_player_sim.py` agreed with
  the server estimate within 0.1 s on single-viewer runs.
- `live_brief` cut heard p95 from 5.8 s to 4.6 s (p50 3.4 s unchanged) and speed-ups from 21 to 12 of about 26
  phrases (one run each).

### Bad

- Content is lost: skipped phrases, condensed translations, and speech at up to 1.3x.
- On dense speech the 1.3x limit is hit often: 19 of 31 Tamil phrases (21 Nov, SPEC section 20); 46 of 185 lines
  with the v1 flags off (24 Nov, `../../v1/LIVE_DENSE_REPORT.md` section 1).
- How 1.3x sounds was never judged by listeners.

## Evidence

- Experiments: [EXP-004](../experiments/EXP-004-heard-vs-first-audio.md), [EXP-024](../experiments/EXP-024-dense-speech-budget.md)
- Commits: `a7f75b3`/`3006847` (audio only with a viewer, skip over 8 s), `a88de86`/`de4a631` (trim, tempo fit,
  heard metric), `0b6d9f8`/`736a4d0` (merge waiting phrases), `d917086`/`70544cf` (show heard delay),
  `ecd2298`/`65bd642` (`live_brief`)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 9, 16, 20; [`LIVE_TEST_REPORT.md`](../../../LIVE_TEST_REPORT.md)
