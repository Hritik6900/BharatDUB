# Roadmap

Now / next / later, dated 2026-11-25. Built from the ordered checklist [`../v1/NEEDS_APPROVAL.md`](../v1/NEEDS_APPROVAL.md)
(27 items; "item N" below is its current number), the product gaps of SPEC section 20, the pending decisions of
`docs/v1/SUMMARY.md` section 4 and `docs/v1/V1_1_SUMMARY.md`, and the targets not reached. Nothing here is a
promise of a date. Open questions behind these items: [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

## Targets not reached

From `docs/v1/ARCHITECTURE.md` (targets), `docs/v1/EVAL_REPORT.md` and `docs/v1/V1_1_SUMMARY.md` (measured).

| Target | Best measured | Label, source, conditions | What would move it |
|---|---|---|---|
| Studio words heard back at least **96%** | 95.9% (HQ); standard 90.6% | measured, V1_1_SUMMARY 2.5, 25 Nov 2026 rerun, three videos, 76 lines, one job per video | a second judge (item 6), labels to tie the score to a listener (item 21), big translation model (item 9) |
| Live first audio p50 at most **1.8 s** | 2.3-2.5 s through the tunnel (v1); 1.8 s with v0's backend on the VM | measured, EVAL_REPORT targets (23 Nov, 3 runs) and SPEC section 21 (21 Nov, one run) | backend on the VM (items 1-2) |
| Live on time at least **90%** | within 1 s: 92.3% with the budget (reached); within 0.25 s: 80.6% with the budget, 56-70% in the 23 Nov eval | measured, LIVE_DENSE_REPORT via V1_1_SUMMARY 2.1 (24 Nov, dense reel, 5 runs a setting); EVAL_REPORT (23 Nov, 3 runs) | `V1_LIVE_BUDGET` (founder's call), backend on the VM, long dense recordings to confirm (item 20) |
| Live skips at most **1 per 10 min** | 7.1 (0-17.9) flags off; 7.8 (0-35.8) with the budget | measured, V1_1_SUMMARY 2.1 | not known; nothing measured reduces it |
| `dur_ratio` p90 at most **1.0** | 1.42 flags off; 1.17 with the budget; 1.09 with budget, controller and engine speed | measured, V1_1_SUMMARY 2.1 | not known |
| Hard-audio key words at least **73 of 80** | hosted 71.3 (71-72); our Whisper 52 (50-55) | measured, EVAL_REPORT targets, 23 Nov 2026, 3 runs | Indic Transcribe (item 11) for Studio; not known for Live |
| Warm and green 5 min after a VM restart | not tested | target only | items 1-3, a rehearsal |

## Now (no VM, minutes each, or a decision)

| # | What | Source |
|---|---|---|
| 1 | Stop the laptop sleeping on AC power (three `powercfg` lines) | item 16; [INC-05](INCIDENTS.md#inc-05-link-stalls-of-24-nov) |
| 2 | Start the tunnel watchdog in report-only mode | item 17 |
| 3 | Stop the five comparison backends on 8111-8115 | item 18 |
| 4 | Switch v1's flags to the recommended set; decide `V1_BREAKER` + `V1_LIVE_DEGRADE` and `V1_LIVE_BUDGET` | [RUNBOOK.md](RUNBOOK.md#flags-and-the-recommended-v1-env); SUMMARY section 4 decision 4 |
| 5 | Choose the English voice (`V1_EN_VOICE`), and whether a stock-voice session may move to the copy when the stock voice fails | item 22; [INC-06](INCIDENTS.md#inc-06-hosted-stock-voice-refusing-lines-http-502) |
| 6 | ~~Decide whether Studio HQ is offered at all without `V1_HQ_REVIEW`~~ decided 26 Nov 2026: never, enforced in code | SUMMARY section 4 decision 6; [INC-07](INCIDENTS.md#inc-07-hq-transcript-damage-found) |

## Next (the GPU machine, in the checklist's order)

| # | What | Items |
|---|---|---|
| 7 | Look at the machine (read-only): processes, memory per process, tools | 1 |
| 8 | Move the v1 backend to the GPU machine; measure Live there once | 2 (Docker, item 3, optional) |
| 9 | QA server on the machine's CPU; the card's numbers on the status page; second judge for Tamil, Bengali and others | 4, 5, 6 |
| 10 | Diarization (accept pyannote's terms, token) | 7 |
| 11 | HQ window: Maya 2 + voice A/B, 12B translation A/B (31B only if 12B wins and only if it fits), batching voice server, Indic Transcribe after the licence decision | 8, 9, 10, 11 |
| 12 | Pin model versions after the first good start | 12 |
| 13 | Measurements only the founder can enable: session start with a recorded voice, a male speaker, English on a healthy night; 2-3 dense 10-minute recordings; 30 labels a language; listeners for the blind test | 19, 20, 21, 26 |
| 14 | Prices for the cost per minute (no figure is shown until rates are set) | 23 |
| 15 | A pitch video of a real stream (how long recordings stay: decided and built 26 Nov 2026, 30 days, [ADR-0034](adr/0034-recording-retention.md)); whether deleting a voice deletes its recordings | 25 |
| 15a | Get written confirmation of commercial use from AI4Bharat / legal review (IndicF5) | 28 |

## Later (product gaps, SPEC section 20)

| # | What | Items / state |
|---|---|---|
| 16 | **Hosting:** domain, HTTPS, demo password; a deploy script; engines that start by themselves after a restart | item 13; compose files written, never run |
| 17 | **Data:** Postgres store instead of one local JSON file; a backup bucket and a rehearsed restore | items 14, 15 |
| 18 | **Accounts:** sign-in; voice profiles and streamer handles tied to a person | not built |
| 19 | **Usage limits, metering and billing** | not built |
| 20 | **Terms, privacy page, takedown** for a misused voice or video | not built |
| 21 | **Monitoring and alerts** beyond the stream watcher | not built |
| 22 | **Capacity:** more than one stream per GPU / per hosted account (one GPU through one tunnel is one stream; hosted account = 1 request at a time) | not measured beyond one test run |
| 23 | **Never-tested paths:** a person at a real microphone for a long session, a real YouTube Live broadcast with outside viewers, a phone on a mobile network, word error rate on ground-truth clips | SPEC section 20 |
| 24 | Speech-to-text fallback for the Standard engine and for non-Hindi sources | [INC-02](INCIDENTS.md#inc-02-hosted-stt-outage) |
| 25 | The hold that grows during stalls and never comes back down: server rule and viewer-page change built 26 Nov 2026 ([ADR-0035](adr/0035-hold-ease-back.md)); **a browser test of the viewer page is still to do** | SPEC section 21; [EXP-030](experiments/EXP-030-hold-ease-back.md) |

Decided in [ADR-0019](adr/0019-v1-on-laptop.md) (revisit with items 1-3), [ADR-0026](adr/0026-gated-models.md),
[ADR-0033](adr/0033-deploy-kit-4gb-rule.md).
