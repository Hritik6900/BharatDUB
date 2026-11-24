# ADR-0005: No voice copy without recorded consent (403); outputs labelled AI-dubbed

- **Status:** accepted
- **Date:** 2026-11-13
- **Superseded by:** —

## Context

The product copies a real person's voice, and a copied voice can be misused. Consent was a golden rule from the
first day (`../../../SPEC.md` section 2, rule 4; section 15).

## Options considered

| Option | Status in the sources | Why it lost or won |
|---|---|---|
| Hard gate: no clone call unless the voice profile has `consent_at`; HTTP 403 otherwise; "no debug bypass" | chosen; SPEC section 2 rule 4, section 15 | — |
| Consent as a UI hint only | not recorded (not evaluated) | — |
| Only Streamer Mode profiles may copy a voice (`live_clone_needs_streamer` on) | built 15 Nov (`f3dc17d`/`8d82653`), **switched off the same day by the user's decision** (`89b68e4`/`10bd8e1`) | `/live` should again be able to copy the stream's voice behind its own consent tick (SPEC section 16, Streamer Mode notes) |

## Decision

- Cloning requires a voice profile with `consent_at`; the backend refuses otherwise with 403 (SPEC section 15).
- How consent is given, per path:
  - `/voices` and Streamer Mode: a consent sentence read aloud and recorded (SPEC section 12;
    `../../../STREAMER_MODE.md`).
  - Studio "voice from the video": `voice_from_video=true` + `voice_consent=true`, a checkbox at upload, not read
    aloud (SPEC section 16, 13 Nov; `55d85d8`/`642e33a`).
  - Live "voice from the stream": `voice_from_stream=true` + `voice_consent=true` (SPEC section 16, 13 Nov).
- Upload requires "I own this video or have permission". Outputs carry "AI-dubbed by Bharat Dub" (first SRT cue and
  a UI label). Uploads are deleted after 24 h; a voice profile is deletable in one click (SPEC section 15).

## Consequences

### Good

- Every later voice path inherited the gate: the GPU voice engines, Streamer Mode, and in v1 the voice A/B kit,
  which refuses a profile without consent on record (`../../v1/PROGRESS.md`, v1.1 WS5).
- v1 does not import v0's voice profiles: their consent records are in v0's store, so voices are recorded again in
  v1 with consent (`../../v1/DISCOVERY.md` risk 5).

### Bad

- The Studio checkbox is weaker than a sentence spoken aloud (SPEC section 16 says so).
- No terms or privacy pages and no way for a third party to report a misused voice (SPEC section 20, 21 Nov).
- Live recordings (ADR-0032) stay until deleted by hand, and deleting a voice profile does not delete recordings
  made in that voice (`../../v1/PROGRESS.md`, v1.1 WS4).

## Evidence

- Commits: `227f031`/`9944394` (`consent_at` in the schema), `55d85d8`/`642e33a` (voice from the video, consent at
  upload), `c401e5a`/`b8fcda3` (Streamer Mode voice with consent), `f3dc17d`/`8d82653` then `89b68e4`/`10bd8e1`
  (streamer-only switch on, then off)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 2, 15, 16, 20;
  [`STREAMER_MODE.md`](../../../STREAMER_MODE.md); [`../SECURITY_AND_CONSENT.md`](../SECURITY_AND_CONSENT.md)
