# ADR-0019: v1 runs on the laptop, not the VM (founder's choice); cost: tunnel latency and link stalls

- **Status:** accepted (revisit: NEEDS_APPROVAL items 1-3)
- **Date:** 2026-11-23
- **Superseded by:** — (to be revisited when `../../v1/NEEDS_APPROVAL.md` items 1-3 are done)

## Context

The v1 design put everything on the GPU machine: Caddy (HTTPS + demo password) in front of web :3100 and backend
:8110, Redis, the store, the shared GPU servers and new ones (`../../v1/ARCHITECTURE.md`, "Layout on the VM").
The build rules forbid sudo, system packages, firewall, DNS and domain changes (rule 8) and route anything that
needs them to `../../v1/NEEDS_APPROVAL.md` (rule 10). The build "was not to open a shell on the machine"
(`../../v1/NEEDS_APPROVAL.md` item 1). Running v1 on the laptop was the founder's choice; no source document
records the reason beyond these rules **(unconfirmed)**.

## Options considered

| Option | Measured / known | Outcome |
|---|---|---|
| v1 on the laptop, GPU servers through v0's SSH forwards | runs; about 0.5 s slower first audio than on the VM (`../../v1/SUMMARY.md` section 1) | **chosen** for the build |
| v1 backend on the GPU machine, website on the laptop | v0 measured once: first audio p50 2.3 s through the tunnel, 1.8 s on the machine (`../../../SPEC.md` section 21) | written (`scripts/v1/vm-backend.sh`), never run; items 1-3 |
| Everything in Docker on the VM | no Docker on the laptop; whether the VM has it is not known (`../../v1/DISCOVERY.md` risk 7) | optional, item 3 |

## Decision

Build and run v1 on the laptop (backend 8110, website 3100) against v0's GPU servers through the existing tunnel.
Everything that needs the VM goes to `NEEDS_APPROVAL.md`, with the backend on the machine as item 2.

## Consequences

### Good

- No risk to the machine v0 depends on; nothing on the VM was started, stopped or installed by v1.

### Bad

- Every phrase crosses the tunnel several times. v1 Live first audio stayed 2.3-2.5 s against the 1.8 s target;
  "no Live flag moves either" (`../../v1/SUMMARY.md` section 2). "What would move the Live numbers... the backend
  on the GPU machine" (same).
- On 24 Nov the GPU services were unreachable three times (2 min, 44 min, 3 h): all three were the laptop in
  Modern Standby (`../../v1/PROGRESS.md`, v1.1 WS0; INC-05). Fix waiting: three `powercfg` lines (item 16).
- No number from v1 may be quoted as the product's until it runs on the VM (`../../v1/SUMMARY.md` section 4,
  decision 5).

## Evidence

- Experiments: [EXP-020](../experiments/EXP-020-v1-live-flags.md), [EXP-023](../experiments/EXP-023-link-stalls-breaker.md),
  [EXP-014](../experiments/EXP-014-standard-vs-gpu-engine.md)
- Commits: `421d133` (scaffold on the laptop), `df27b93` (`vm-backend.sh` written, not run)
- Sources: [`ARCHITECTURE.md`](../../v1/ARCHITECTURE.md); [`SUMMARY.md`](../../v1/SUMMARY.md);
  [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) items 1-3, 16; [INC-05](../INCIDENTS.md#inc-05-link-stalls-of-24-nov)
