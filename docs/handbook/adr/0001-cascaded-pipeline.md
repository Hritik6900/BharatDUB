# ADR-0001: Cascaded pipeline (separate, transcribe, translate, speak, fit, mix) instead of end-to-end speech-to-speech

- **Status:** accepted
- **Date:** 2026-11-13
- **Superseded by:** —

## Context

Bharat Dub turns Hindi/Hinglish speech into Tamil, Bengali, Telugu, English and other Indian languages, in the
speaker's own voice, with captions and with the background music kept. Studio works on uploaded videos of up to
3 minutes; Live runs 3-5 s behind a speaker (`../../../SPEC.md` section 1, target table).

The product also needs things that sit between the steps, not at the ends:

- a glossary of words never translated (SPEC section 7, LLM prompt rules);
- captions published before the audio "so the UI feels instant" (SPEC section 9);
- a review editor where editing one translated line re-runs only voice, fit, mix and render for that line
  (SPEC section 2, rule 3; section 8);
- consent checked before any voice copy (SPEC section 2, rule 4);
- the music track kept under the dub (SPEC section 8, stage 3).

The first prototype (`reel_dubber.py`, single file, named in SPEC section 5) was already a chain of stages.
The 13 Nov build ported it into `studio/stages/` (`227f031`/`9944394`, `df1fa91`/`f488544`).

## Options considered

| Option | Status in the sources | Why it lost or won |
|---|---|---|
| Cascade: separate (Demucs), segment (Silero VAD), transcribe, translate, speak, fit, mix, render | chosen; SPEC sections 8 and 9 | every intermediate is text or a stem we can cache, show, edit and measure |
| End-to-end speech-to-speech translation model | **not recorded; not evaluated** | no comparison exists in any doc or commit |
| A hosted dubbing service as one black box | **not recorded; not evaluated** | — |

Reasoning for rejecting end-to-end **(unconfirmed, reconstructed)**: the features listed above all need a text
transcript and a text translation in the middle (captions, glossary, line edit, and since 14 Nov "English words
in the target script" for the voice engine, SPEC section 16). A single speech-to-speech model gives none of these
handles, and none was known to speak Hinglish into ten Indian languages in a copied voice. No source writes this
down; it is inferred from what the cascade is used for.

## Decision

Every mode runs the same chain of separate stages, each behind a provider interface (ADR-0002): speech-to-text,
translation, voice, plus local audio steps (separation, VAD, tempo fit, mix). Live is the same chain cut into
phrases (ADR-0006, ADR-0008).

## Consequences

### Good

- Each stage is timed and swappable. On 21 Nov speech-to-text and translation moved to our own GPU for one engine
  without touching the pipelines (ADR-0014, ADR-0015).
- Text in the middle gives captions, the glossary, the review editor and the Studio cache (ADR-0003).
- Studio pays for only three steps per use: speech-to-text, translation, voice (pitch PDF, 15 Nov, part A2).

### Bad

- Latency adds up. Hosted mode, one line of the dense reel: speech-to-text about 1.0 s, translation 0.85-0.95 s,
  voice about 1.0 s (**measured**, SPEC section 21, 21 Nov; n not stated).
- Errors compound: a misheard subject word is translated and then spoken (real stream, 21 Nov, SPEC section 21,
  "Open, seen in that stream's transcript").
- The dub's length is set by the translator and the voice, not by the source. Tamil dub 64.4 s for 50.3 s of
  speech (**measured**, 14 Nov, SPEC section 16, one run). This became the main Live problem (ADR-0008, ADR-0028).

## Evidence

- Experiments: [EXP-014](../experiments/EXP-014-standard-vs-gpu-engine.md),
  [EXP-018](../experiments/EXP-018-prisma-vs-whisper-hard-audio.md),
  [EXP-004](../experiments/EXP-004-heard-vs-first-audio.md)
- Commits: `227f031`/`9944394` (M0 + M1), `df1fa91`/`f488544` (M2 Studio stages)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 1, 2, 5, 8, 9, 16, 21;
  [pitch PDF](../../../pitch/BharatDub_Architecture_Costs_Questions.pdf) (15 Nov, parts A1-A2)
