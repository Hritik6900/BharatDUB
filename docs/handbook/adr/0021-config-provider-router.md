# ADR-0021: Config-driven provider router (`routing.yaml`) reproducing v0 exactly

- **Status:** accepted
- **Date:** 2026-11-23
- **Superseded by:** —

## Context

In v0, provider choice was a fixed table in `providers/__init__.py`: per engine (`cloud` / `gpu`) and step, a
provider with its fallback (`../../v1/DISCOVERY.md` section 2). v1 needed different provider lists per mode
(Live, Studio, Studio HQ), new servers (9041-9045), and timeouts per step, without code edits for each change.

## Options considered

| Option | Outcome |
|---|---|
| Keep extending v0's fixed table in code | kept as the path when `V1_ROUTER` is off, and as the fallback if the file is broken |
| Provider order, timeouts and fallbacks per step, mode and engine in `backend/config/routing.yaml` | **chosen**, behind `V1_ROUTER` |

## Decision

- `backend/config/routing.yaml` + `app/v1/router.py` (reads and checks the file, builds the providers, leaves out
  one whose address or key is not set) + `app/v1/stages.py` (`transcribe()`, `translate()`, `speak()`,
  `separate()`, `diarize()`, `score()`: each walks its list with a timeout per provider and logs why it moved on).
- A job's voice stays with the provider that spoke its first line.
- The shipped file must build exactly v0's providers. `GET /api/v1/routing` shows the result.

## Consequences

### Good

- Checked by 17 tests: for five setups (nothing configured, hosted only, hosted + voice engine, everything, GPU
  machine without hosted keys), both engines and both modes, the shipped file builds the same provider objects as
  v0's table, same classes and order of fallbacks. Bad files are refused; a broken file at run time falls back to
  v0's table (`../../v1/PROGRESS.md` phase 4).
- One Live run with it on (**measured** 23 Nov, one run): same providers in the trace; first audio p50 2.4 s
  against 2.7 s off; 74% within 0.25 s and 85% within 1 s against 76% / 89%: inside run-to-run spread.
- Recommended on: needed so the HQ path's provider lists change in one file (`../../v1/SUMMARY.md` section 2).

### Bad

- A second place where provider choice lives; the breaker (ADR-0027) had to be attached in both the router and
  v0's table.
- A dropped request once moved a whole job's Bengali lines (13) to the hosted copy of the voice, because a job
  keeps the voice that spoke first; fixed by trying the job's own voice twice (`../../v1/PROGRESS.md` phase 8).

## Evidence

- Experiments: [EXP-020](../experiments/EXP-020-v1-live-flags.md)
- Commits: `866aa45` (router), `5908ec9` (tests force flags off)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) phases 4 and 8; [`DISCOVERY.md`](../../v1/DISCOVERY.md) section 2;
  [`routing.yaml`](../../../backend/config/routing.yaml)
