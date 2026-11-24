# ADR-0011: Borrowed A100 40 GB VM reached by SSH tunnels from the laptop; one tunnel per kind of traffic

- **Status:** accepted
- **Date:** 2026-11-14
- **Superseded by:** —

## Context

The voice engine (ADR-0010) needs a GPU; the backend and website run on one laptop (`../../../SPEC.md` section 20,
"Hosting"). The GPU available is an A100 40 GB on a shared machine ("a shared machine behind an SSH tunnel",
SPEC section 20). The address is kept in `../../v1/NEEDS_APPROVAL.md`, not here. The engines bind the machine's
loopback only (`../../v1/DISCOVERY.md` section 1).

## Options considered

| Option | Status in the sources | Outcome |
|---|---|---|
| SSH port forwards from the laptop to the engines' loopback ports | chosen 14 Nov | below |
| Backend on the GPU machine, website on the laptop | measured once 21 Nov: first audio p50 1.8 s against 2.3 s through the tunnel (SPEC section 21) | not adopted yet: see ADR-0019, `NEEDS_APPROVAL.md` items 1-3 |
| Public HTTPS endpoints on the machine | not recorded (not evaluated) | — |
| Hosted GPU inference service | not recorded (not evaluated) | — |

## Decision

- `gpu_engine/tunnel.ps1` opens SSH forwards for ports 9001-9003 (voice), 9010 (separation), 9020 (translation),
  9030 (speech-to-text); self-reconnecting since 14 Nov (`7fba6ab`/`bdd272f`).
- Since 21 Nov, one SSH connection per kind of traffic (`9fae6c8`): on the 67-minute stream one stalled packet held
  speech-to-text, translation and voice up together.

## Consequences

### Good

- No hosting, domain or firewall work was needed to use the GPU.
- The machine was replaced on 20 Nov and the engines rebuilt from `gpu_engine/` (`setup_machine.sh`), with nothing
  changed on the laptop side but the address (SPEC section 17).

### Bad

- Each request costs more than the network: median 410 ms through the tunnel although the round trip is 170 ms
  (**measured** 20 Nov, SPEC section 17). A line from the laptop: 0.79 s, of which network 0.32 s (21 Nov).
- On the 67-minute real stream (21 Nov) every bad stretch sat on a stall of the laptop-to-machine link; 94 lines
  (7%) took more than 4.5 s (**measured**, SPEC section 21). INC-04 in [`../INCIDENTS.md`](../INCIDENTS.md).
- On 24 Nov all GPU services were unreachable three times (2 min, 44 min, 3 h): the laptop was in standby
  (`../../v1/PROGRESS.md`, v1.1 WS0; [INC-05](../INCIDENTS.md#inc-05-link-stalls-of-24-nov)).
- One GPU through this tunnel is one stream: a second session beside a real stream dropped its within-1 s share
  from 80% to 56% (21 Nov, SPEC section 21).
- The engines do not start by themselves after a restart (SPEC section 20).

## Evidence

- Experiments: [EXP-016](../experiments/EXP-016-real-stream-67min.md), [EXP-023](../experiments/EXP-023-link-stalls-breaker.md),
  [EXP-014](../experiments/EXP-014-standard-vs-gpu-engine.md)
- Commits: `770112f`/`b674dca` (engine behind the tunnel), `7fba6ab`/`bdd272f` (self-reconnecting tunnel),
  `0143cbd` (machine replaced), `9fae6c8` (one connection per traffic)
- Sources: [`SPEC.md`](../../../SPEC.md) sections 17, 20, 21; [`DISCOVERY.md`](../../v1/DISCOVERY.md) section 1;
  [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) Part A
