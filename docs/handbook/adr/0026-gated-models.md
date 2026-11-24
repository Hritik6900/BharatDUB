# ADR-0026: Indic Transcribe, pyannote gated on licence/terms; Maya 2 and big translation model wait for a GPU window

- **Status:** proposed
- **Date:** 2026-11-23
- **Superseded by:** —

## Context

v1 planned new model servers on 9041-9045: batching voice server, Maya 2, Indic Transcribe, a big translation
model for Studio HQ, and a QA server (`../../v1/ARCHITECTURE.md`, port map). The A100 has 40 GB; v0's servers hold
about 34 GB, so about 6 GB is free, and a new model may load only if 4 GB stays free afterwards: "That allows
nothing above 2 GB" (`../../v1/MODELS.md` summary; ADR-0033). Licences were checked on 23 Nov and again on 25 Nov.

## Options considered

From `../../v1/MODELS.md` (cards' own figures, not ours; nothing was loaded):

| Model | Licence | Size / GPU (card or estimate) | Status |
|---|---|---|---|
| Indic Transcribe Core (`bodhan-ai/indic-transcribe-core`, 1.2 B) | Indic Open Model License v1.0, gated; self-hosting yes, **a hosted service others call needs written sign-off** | 9.2 GiB at batch 8 (card) | waits: licence decision + HQ window (item 11) |
| pyannote `speaker-diarization-community-1` | CC-BY-4.0, gated (accept terms, token) | CPU | waits: terms + token (item 7) |
| Maya 2 Native (2.5 B) | Apache-2.0 | 7.7 GB steady, 9.2 GB loading (card) | waits: GPU window, keep-or-drop by ear (item 8) |
| Gemma 4 12B / 31B QAT w4a16 | Apache-2.0 tag | 10.3 GB / 23.3 GB on disk; 14 / 27 GB with cache (our estimate) | waits: HQ window; 12B first (item 9) |
| IndicConformer 600M | MIT, gated | 2.55 GB | not used: its own card recommends Indic Transcribe |
| MelBand RoFormer vocals | unsettled (MIT tag, none in repo, CC-BY-NC-SA per one third party) | — | not adopted |

## Decision (proposed)

- Do not load any of these beside v0 now. Each is an item in `../../v1/NEEDS_APPROVAL.md` with commands, expected
  memory and rollback.
- Indic Transcribe: samples and pitch only until its authors sign off, else keep the hosted speech-to-text.
- Big translation model: 12B first; 31B only if 12B wins by the rule written in `backend/eval/v1/llm_ab.py`
  before any result (preferred in >= 60% of >= 40 decided pairs, no language under 50%, and more).
- Maya 2: a Studio HQ candidate voice; it has no speed control and needs the sample's exact words, like IndicF5.

## Consequences

### Good

- No licence risk taken on and no risk to v0's GPU memory.
- Stub modes let every server be tested through the backend's real clients without the model
  (`../../v1/PROGRESS.md` phase 6).

### Bad

- Studio HQ runs its text steps on the small model; 96% not reached (ADR-0024).
- 31B does not fit by the estimates: an HQ window leaves about 24 GB; 27 + 4 = 31 GB.
- The 12B checkpoint's page reports start failures on vLLM with no working version named; v0 runs vLLM 0.34.0.
- None of the real model paths has ever run (batched IndicF5, Maya, Indic Transcribe).

## Evidence

- Commits: `bb71d9a` (servers, stubs, `MODELS.md`), `ddb8d59`/`df27b93` (deploy kit, A/B kits)
- Sources: [`MODELS.md`](../../v1/MODELS.md); [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) items 7-11, 24;
  [`ARCHITECTURE.md`](../../v1/ARCHITECTURE.md) rules 6, 12
