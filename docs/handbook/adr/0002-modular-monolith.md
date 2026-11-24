# ADR-0002: One FastAPI backend + one Next.js site; providers behind interfaces

- **Status:** accepted
- **Date:** 2026-11-13
- **Superseded by:** —

## Context

Three modes (Studio, Live, Streamer) share one voice profile, one glossary and the same AI providers
(`../../../SPEC.md` section 1). Live has a 3-5 s budget from speaker to viewer (SPEC section 1). M0-M5 were built
by one engineer in one day (13 Nov, git log).

## Options considered

| Option | Status in the sources | Why it lost or won |
|---|---|---|
| API-first modular monolith: one FastAPI process, one Next.js site | chosen; SPEC section 2, rule 1 | the live audio path stays in memory with no network hop between steps, "which matters with a 3 to 4 s budget" (pitch PDF, 15 Nov, part A1) |
| Microservices / Kubernetes | rejected by SPEC section 2, rule 1 ("No microservices, no Kubernetes") | no reason written beyond the rule; one engineer on one laptop **(unconfirmed, reconstructed)** |
| Pipelines calling vendor APIs directly | rejected by SPEC section 2, rule 2 | a provider could not be swapped or mocked "without touching a pipeline" (pitch PDF, A1) |

## Decision

- One FastAPI backend (`backend/app/`), one Next.js site (`web/`).
- The one separate service is the GPU engine (`gpu_engine/`), optional, reached only through `providers/`; with it
  off everything still runs (SPEC section 2, rule 1, as amended after 14 Nov).
- Every speech-to-text, translation and voice call goes through `backend/app/providers/` behind the Protocols of
  SPEC section 7 (`STT`, `StreamingSTT`, `LLM`, `TTS`). Each external call has a timeout, one retry and a visible
  fallback (SPEC section 2, rule 8). All hosted Gnani calls pass one process-wide gate because the account allows
  one active request at a time (SPEC section 6).

## Consequences

### Good

- Providers were swapped without touching the pipelines: Gemini for translation (13 Nov, ADR-0007), IndicF5 for
  the copied voice (14 Nov, ADR-0010), Whisper and Gemma for the GPU engine (21 Nov, ADR-0015).
- Mock providers made the whole site testable offline (SPEC section 19: 42 backend tests on 13 Nov,
  `MOCK_PROVIDERS` mode).
- v1 could put a config-driven router in front of the same layer (ADR-0021).

### Bad

- One process holds all state. The local store is one JSON file in that process's memory; two processes on the
  same file overwrite each other (`../../v1/DISCOVERY.md` section 4 and risk 6; ADR-0004).
- Studio jobs and Live sessions share the process; a heavy Studio job beside a live stream was not measured.
- The GPU engine is a second thing to deploy and reach (ADR-0011).

## Evidence

- Commits: `227f031`/`9944394` (scaffold, providers), `e4728b7`/`d7af258` (M3 live pipeline), `31673b9` (engine per session through `providers/`)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 2, 5, 7, 19;
  [`DISCOVERY.md`](../../v1/DISCOVERY.md) sections 2-4 and risks;
  [pitch PDF](../../../pitch/BharatDub_Architecture_Costs_Questions.pdf) (15 Nov, part A1)
