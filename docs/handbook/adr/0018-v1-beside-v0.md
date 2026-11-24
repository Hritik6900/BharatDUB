# ADR-0018: v1 built beside v0, never replacing it: worktree, branch, ports 3100/8110, own data/env; v0 frozen at `v0-baseline`

- **Status:** accepted
- **Date:** 2026-11-23
- **Superseded by:** —

## Context

By 22 Nov v0 (branch `main`) was the product people used, including real streams (SPEC section 21). v1 was to
bring better pitch samples, a stable demo and real numbers, with code shaped for production
(`../../v1/ARCHITECTURE.md`, "DESIGN"). The first rule of v1: "v0 must keep working at all times"
(`../../v1/ARCHITECTURE.md`, rule 1). The v1 documents call the product "BharatDb"; it is the same Bharat Dub.

## Options considered

| Option | Outcome |
|---|---|
| Develop v1 on `main` in v0's folder | rejected: any change risks the running product |
| Second git worktree on branch `v1`, own ports, data and env, v0 tagged | **chosen** |
| A copy on the GPU machine | deferred (ADR-0019) |

## Decision

- v0 frozen at tag `v0-baseline` = `80c36d8` (22 Nov). v1 in a second worktree, branch `v1`.
- v1 ports: website 3100, backend 8110, comparison backends 8111+, new model servers 9041-9045. Never bind 3000,
  8010 or 9001-9040 (`../../v1/ARCHITECTURE.md` rule 4).
- v1 only *calls* v0's GPU servers; never edits `gpu_engine/` or v0's dev script; never reads or writes v0's data
  (rules 1-3). Own `backend/.env` (keys copied, never printed), own data folder.
- After every phase, v0 is checked through its health endpoints (`scripts/v1/v0-check.sh`).

## Consequences

### Good

- v0 answered every check after every phase and workstream: "all nine checks ok" (`../../v1/PROGRESS.md`, phases
  1-9 and v1.1 WS0-WS6).
- Roll back is cheap: switch a flag off or stop v1; v0 on 3000 and 8010 is as it was (`../../v1/SUMMARY.md` section 5).

### Bad

- No test session on v0 itself: running one on port 8010 was refused, so "v0" in every comparison is v1 with every
  flag off (`../../v1/PROGRESS.md` phase 8).
- v1 shares v0's GPU servers and the one-request hosted account; a v1 run beside a live v0 stream makes both worse,
  so v1 runs only when no v0 session is live (`../../v1/DISCOVERY.md` risks 1-2).
- Voice profiles are not imported: their consent records are in v0's store; voices are recorded again in v1
  (`../../v1/DISCOVERY.md` risk 5).
- Two checkouts to keep in mind; five comparison backends were left running on 8111-8115 at one point
  (`../../v1/NEEDS_APPROVAL.md` item 18).

## Evidence

- Commits: `80c36d8` (v0 baseline), `92638c1` (v1 setup rules), `dcb3171` (discovery and plan), `421d133`
  (scaffold beside v0)
- Sources: [`ARCHITECTURE.md`](../../v1/ARCHITECTURE.md) rules 1-4; [`DISCOVERY.md`](../../v1/DISCOVERY.md);
  [`PLAN.md`](../../v1/PLAN.md); [`SUMMARY.md`](../../v1/SUMMARY.md) sections 1, 5;
  [`PROGRESS.md`](../../v1/PROGRESS.md) setup and phases
