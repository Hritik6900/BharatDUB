# ADR-0032: Live dub stored only with flag + per-session ask (pitch kit)

- **Status:** accepted
- **Date:** 2026-11-25
- **Superseded by:** —

## Context

A pitch needs a video of a real session: original beside dubbed, with that session's own numbers. But the spec
says "Live audio is never stored" (`../../../SPEC.md` section 10), and a recording holds the speaker's copied voice
and their words (`../../v1/PROGRESS.md` v1.1 WS4, "Decided").

## Options considered

| Option | Outcome |
|---|---|
| Record every session | rejected: breaks SPEC section 10 and consent (ADR-0005) |
| Screen-capture a viewer page | not recorded (not evaluated) |
| Record only when the backend flag is on **and** the session asks for it | **chosen** |

## Decision

- `V1_LIVE_RECORD` (default off) + `record: true` on `POST /api/live/sessions`. The `/live` console shows a tick
  "Keep a recording of this session's dub on this server" only while the flag is on, never ticked by itself, with
  what is kept and that it stays until someone deletes it.
- Kept under `<DATA_DIR>/recordings/<session>/`: one mono track per language on the session clock, `phrases.jsonl`
  (timings, caption text), `session.json`. The stream's own sound is not kept. Caption text stays in that folder
  only: not in the trace, the store or `logs/`.
- `scripts/v1/render-pitch.ps1` makes the side-by-side video; every number on the picture is computed from that
  recording's `phrases.jsonl`. "On time" is shown as within 0.25 s with within 1 s beside it, both labelled.
- `V1_LISTEN_TEST`: a blind A/B listening page; listener ids are random browser strings, no names.

## Consequences

### Good

- One recorded session proved the chain (**measured** 25 Nov, dense reel 3 times, Punjabi, `V1_LIVE_BUDGET` on,
  one run): 36 phrases in 35 voice calls, none skipped; first audio 2.3 s; 91.4% within 0.25 s / 97.1% within 1 s
  (picture and trace agree); 33 of 35 lines in the copied voice. Rendered video 82.1 s, 35.3 MB.
- Flag off, or no per-session ask: nothing written anywhere (tested).

### Bad

- A recording is never deleted by itself, and deleting a voice profile does not delete recordings made in it.
  How long recordings stay is undecided (`../../v1/NEEDS_APPROVAL.md` item 25).
- Viewers on `/watch` are not told a session's dub is being kept (nothing of theirs is in it).
- The listening page has no sign-in; one person can answer as several. Fine among invited listeners, not a poll.
- The example is the test reel, not a real stream; render time was not measured.

## Evidence

- Experiments: [EXP-028](../experiments/EXP-028-pitch-recording.md)
- Commits: `bc48922` (WS4)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) v1.1 WS4; [`V1_1_SUMMARY.md`](../../v1/V1_1_SUMMARY.md) section 2.7;
  [`SPEC.md`](../../../SPEC.md) section 10; [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) items 25-26
