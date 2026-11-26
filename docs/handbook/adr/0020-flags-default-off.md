# ADR-0020: Every new behaviour behind a flag, default off; tests force flags off

- **Status:** accepted
- **Date:** 2026-11-23
- **Superseded by:** — (three exceptions since 26 Nov 2026, v1.2 Part 1: `V1_HQ_ADAPTIVE` defaults to on, an HQ job is
  always reviewed whatever `V1_HQ_REVIEW` says, and the hold's way back is on behind the kill switch `LIVE_SYNC_EASE`:
  [ADR-0035](0035-hold-ease-back.md))

## Context

v1 changes the same `backend/` and `web/` code v0 runs (`../../v1/ARCHITECTURE.md` rule 2), and v0 must keep
working (rule 1). Every change had to be measurable against "as v0 does it" and easy to undo.

## Options considered

| Option | Outcome |
|---|---|
| Change behaviour directly on branch `v1` | rejected: no clean "v0" to compare against, no quick roll back |
| Every new behaviour behind a flag in v1's `.env`, default off; flags-off path = v0's code path | **chosen** (`../../v1/ARCHITECTURE.md` rule 5; `../../v1/PLAN.md`) |
| Separate code tree for v1 | used only for new GPU servers (`gpu_engine_v1/`) |

## Decision

- Flags live in `backend/app/v1/flags.py` and `backend/app/config.py`; code defaults are off.
- With all flags off the code path is v0's. Each workstream has a test that says so (e.g.
  `test_flags_off_nothing_new_is_asked_stored_or_built`, `../../v1/PROGRESS.md` v1.1 WS1).
- The test run forces every v1 flag off whatever the local env file says (`5908ec9`: "the phase 4 commit went out
  with one test failing for that reason; all 120 pass now"). Comparison backends (`scripts/v1/ab-server.*`) force
  unlisted flags off too.
- The recommended set is written down, not switched on by code (`../../v1/RUNBOOK.md` section 3; ready block in
  `backend/.env.example`).

## Consequences

### Good

- "v0" in every v1 measurement is v1 with all flags off: same providers, same pipeline (`../../v1/SUMMARY.md` section 1).
- Roll back is a flag and a restart, for every workstream (`../../v1/PROGRESS.md`, "Roll back" lines).
- Flags without a gain could be removed cleanly (ADR-0029).

### Bad

- Many flags: 26 on/off flags plus `V1_STORE` in `backend/app/v1/flags.py` at `e4944fd`, several marked
  "your call" in `../../v1/SUMMARY.md` section 2.
  Combinations were mostly not measured together (e.g. WS1 flags with WS0's, `../../v1/PROGRESS.md` v1.1 WS1).
- `Settings` uses `extra="ignore"`: a removed or misspelt flag name in the env file is skipped without a warning
  (`../../v1/PROGRESS.md` v1.1 WS6).
- A recommended flag can change what other numbers mean: with `V1_LIVE_STOCK_DEFAULT` on, a `/live` session never
  learns a voice, while every v1.1 Live number was measured with a learned voice (`../../v1/SUMMARY.md` section 2).

## Evidence

- Commits: `421d133` (flags, all off), `5908ec9` (tests force flags off), `e3128ef` (two flags removed)
- Sources: [`ARCHITECTURE.md`](../../v1/ARCHITECTURE.md) rule 5; [`PLAN.md`](../../v1/PLAN.md);
  [`SUMMARY.md`](../../v1/SUMMARY.md) section 2; [`RUNBOOK.md`](../../v1/RUNBOOK.md) section 3;
  [`backend/app/v1/flags.py`](../../../backend/app/v1/flags.py)
