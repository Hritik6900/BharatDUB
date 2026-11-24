# ADR-0022: Trace per phrase/line and a `logs/` folder of measurements only, nothing said

- **Status:** accepted
- **Date:** 2026-11-23
- **Superseded by:** —

## Context

v0 stored timings per Live chunk in `live_chunks` and per Studio stage (`../../../SPEC.md` section 2, rule 5), but
not which provider did each step, whether a fallback answered, or how much GPU time a minute used. Cost per
dubbed minute was not measured (SPEC section 20). The "harder Live and voice checks were scripts outside the
repository" (`../../v1/DISCOVERY.md` section 5). At the same time, nothing said by a speaker may be kept beyond what
the product needs (SPEC section 10: "Live audio is never stored").

## Options considered

| Option | Outcome |
|---|---|
| Keep only v0's per-chunk timings | not enough to see fallbacks, providers or GPU seconds |
| Trace per Live phrase and Studio line (`V1_TRACE`, JSONL + Prometheus) | **chosen** 23 Nov |
| A `logs/` folder in git with per-request, per-phrase and per-job measurements of v0 and v1 runs | **chosen** 24 Nov |
| Keep transcripts and translations in the logs | rejected: "Measurements only. Nothing that was said is kept here" (`../../../logs/README.md`) |

## Decision

- `V1_TRACE`: `app/v1/trace.py` writes one record per phrase and language (trace id, times, providers, fallback per
  step, GPU seconds) and per voiced Studio line; `GET /metrics`, `/api/v1/metrics/summary`, page `/metrics-ui`.
- Cost per minute = GPU seconds x hourly rate + hosted usage x rates; rates are settings, 0 until set, so no cost
  is shown (`../../v1/PROGRESS.md` phase 3).
- `logs/` (`b2a091c`): `api/` (one line per outbound request, `V1_API_LOG`), `sessions/` and `sessions/index.csv`
  (per phrase and per session-language, v0 and v1), `jobs/index.csv`, `trace/`, `streams/` (watcher). No source
  text, translation, audio, voice sample, key, voice or token id.

## Consequences

### Good

- One traced session (**measured** 23 Nov, Tamil + Bengali, 56 s): 44 records, 40 spoken, first audio p50 2.7 s,
  translation p50 0.55 s, 76% within 0.25 s, 89% within 1 s, 95% in the copied voice, 46 s of GPU work for
  0.74 stream minutes (`../../v1/PROGRESS.md` phase 3).
- Real v0 streams of 24 Nov could be read from `logs/` without keeping anything said (EXP-022).
- v1.1 added `dur_ratio` and `backlog` per phrase, which made the dense-speech work possible (ADR-0028).

### Bad

- No cost figure yet: no rates are set (`../../v1/NEEDS_APPROVAL.md` item 23).
- `V1_API_LOG` writes inside the repository and its cost per request was never measured (`../../v1/PROGRESS.md` v1.1 WS6).
- Trace files are large JSONL; old ones keep fields of removed flags (ADR-0029).

## Evidence

- Experiments: [EXP-022](../experiments/EXP-022-real-streams-24nov.md)
- Commits: `7e96f13` (trace and numbers), `b2a091c` (logs folder)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) phase 3, v1.1 WS1, WS6; [`logs/README.md`](../../../logs/README.md);
  [`SPEC.md`](../../../SPEC.md) sections 2, 10, 20
