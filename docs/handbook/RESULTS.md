# Results

The scoreboard of Bharat Dub: the latest measured value of every number we track, with its target, date,
conditions and source. Written 2026-11-25. Each number is quoted as its source gives it.

**Labels.** **measured**: from our own runs. **estimate**: worked out from measured numbers or worded "about".
**target**: what we aim for, not reached unless the row says so. **stand-in**: a price taken from another vendor
because ours is not published; not a real cost.

**Read this before quoting anything.**

- Most Live numbers come from **one dense 24.9 s Hindi reel replayed at real-time speed** (the speaker talks
  85-89% of the time, about 5 words a second). Not a person at a microphone, not a broadcast with outside viewers.
  Two equal runs have differed by about 10 points in timing and 6 in words heard back.
- Studio numbers come from three 50 s test videos whose speech was made by hosted stock voices, and the same reel.
- "v0" numbers measured with the **backend on the GPU machine** are not the laptop setup that v0 and v1 actually
  run on (backend on the laptop, GPU through an SSH tunnel).
- No v1 number is a product number yet: v1 has not run on the GPU VM ([ADR-0019](adr/0019-v1-on-laptop.md)).
- "Words heard back" = the share of a dubbed line's words that the hosted speech-to-text returns. It is not a
  listener, and it cannot see a wrong transcript ([EXP-027](experiments/EXP-027-hq-judge-rerun.md)).
- "Within 0.25 s / 1 s / 2 s" = share of phrases whose dub starts that close to the video moment the phrase was
  spoken at (sync mode). v1 calls "on time" the 0.25 s figure; the WS1 target is set on the 1 s figure.

## Scoreboard

### Live

| Metric | Value | Target | Date | Conditions | Source | Label |
|---|---|---|---|---|---|---|
| First audio p50 / p95, hosted engine | 2.8-2.9 s / 3.9-4.1 s | p50 1.8 s | 2026-11-21 | dense reel 6 loops, Tamil + Bengali, voice learned from stream, hold 6 s, backend on laptop, 2 runs | `SPEC.md` s.21, [EXP-014](experiments/EXP-014-standard-vs-gpu-engine.md) | measured |
| First audio p50 / p95, GPU engine through the tunnel | 2.3 s / 3.0 s | p50 1.8 s | 2026-11-21 | as above, all-GPU, 1 run; before the hosted speech-to-text was put first | `SPEC.md` s.21, [EXP-014](experiments/EXP-014-standard-vs-gpu-engine.md) | measured |
| First audio p50 / p95, backend on the GPU machine | 1.8 s / 2.1 s | p50 1.8 s (reached in this setup only) | 2026-11-21 | as above, no hosted key, 1 run; **not the laptop setup**; not repeated in v1 | `SPEC.md` s.21, [EXP-014](experiments/EXP-014-standard-vs-gpu-engine.md) | measured |
| First audio p50 / p95, GPU engine, latest flags-off baseline | 2408 ms (2308-2496) / 3924 ms (3607-4364) | p50 1.8 s: not reached | 2026-11-24 | dense reel 8 loops, Punjabi + Tamil, hold 6 s, laptop + tunnel, 5 runs | [LIVE_DENSE_REPORT.md](../v1/LIVE_DENSE_REPORT.md) s.4, [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| First audio p50 / p95, with `V1_LIVE_BUDGET` | 2627 ms (2517-2749) / 4403 ms (3773-5078) | p50 1.8 s: not reached | 2026-11-24 | as above, 5 runs | [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| Within 0.25 s / 1 s / 2 s, flags off | 63.5% / 86.5% / 93.9% | 1 s: 90% | 2026-11-24 | as above, 5 runs (ranges 57.9-68.6 / 84.2-90.6 / 92.6-95.3) | [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| Within 0.25 s / 1 s / 2 s, `V1_LIVE_BUDGET` | 80.6% / 92.3% / 95.3% | 1 s: 90% (**reached**, 7 of 10 runs at 90%+) | 2026-11-24 | as above, 5 runs (ranges 77.8-83.6 / 89.8-96.1 / 93.7-96.7) | [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| Within 0.25 s / 1 s / 2 s, all-GPU (tunnel / GPU machine / hosted) | 78 / 96 / 100%; 76 / 93 / 100%; 61-63 / 87 / 93-97% | 90% | 2026-11-21 | dense reel 6 loops, Tamil + Bengali, 1 run each (hosted 2 runs) | `SPEC.md` s.21 | measured |
| dur_ratio p90 (dubbed seconds / source slot) | 1.42 off; 1.17 budget; 1.11 budget + controller | 1.0: **not reached** | 2026-11-24 | dense reel 8 loops, Punjabi + Tamil, 5 runs | [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| Skips per 10 min (phrases dropped as too late) | 7.1 (0-17.9) off; 7.8 (0-35.8) budget | 1: **not reached** in any setting | 2026-11-24 | as above; skips come in bursts behind stalls, none in 11 of 20 runs | [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| Copied-voice share (GPU engine, voice learned from stream) | 97.4% off; 96.1% budget | — | 2026-11-24 | as above, about 185 lines a run | [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| Copied-voice share, all-GPU | 158 of 160 (tunnel); 163 of 163 (GPU machine) | — | 2026-11-21 | dense reel 6 loops, Tamil + Bengali, 1 run each | `SPEC.md` s.21 | measured |
| Words heard back, Live, GPU engine | Punjabi 87.7%, Tamil 84.4% (off); 80.1% / 82.9% (budget + controller) | — | 2026-11-24 | 40 lines a cell from 2 runs; counting rule before the 25 Nov correction, not re-scored | [EXP-024](experiments/EXP-024-dense-speech-budget.md) | measured |
| Words heard back, Live, hosted vs all-GPU | hosted 77-81% / 78-79%; tunnel 82% / 73%; GPU machine 80% / 72% (Tamil / Bengali) | — | 2026-11-21 | dense reel 6 loops, `scripts/live_quality.py`, old rule | `SPEC.md` s.21 | measured |
| Session start: first audio p95 of the first 10 phrases | 3.80 s (3.40-4.34) warm start vs 4.27 s (3.67-5.05) off | — | 2026-11-25 | dense reel twice, Punjabi + Tamil, 5 runs each way; "off" alone moved 0.41 s between batches: **not a proven gain** | [EXP-025](experiments/EXP-025-session-warm-start.md) | measured |
| Link stall (50 s, all GPU endpoints): phrases dubbed during it | 4 of 22 (flags off, 1 run); all of 23-24, stock voice (breaker + ladder, 3 runs) | — | 2026-11-24 | local relay standing in for a stalled tunnel, dense reel, Tamil | [EXP-023](experiments/EXP-023-link-stalls-breaker.md) | measured |
| Link stall: first audio median during it; copied voice back after | 8.2 s (off) vs 3.1-3.5 s (on); back 5.6 s after the link returned (final build, 1 run) | — | 2026-11-24 | as above | [EXP-023](experiments/EXP-023-link-stalls-breaker.md) | measured |
| English lines: changes of voice per session | 9 (7-11) off; 1 (`copy`); 0 (`stock`) | — | 2026-11-25 | dense reel 8 loops, English + Punjabi, 3 runs each, hosted stock voice failing that night | [EXP-026](experiments/EXP-026-english-voice-mix.md) | measured |

### Streamer Mode

| Metric | Value | Target | Date | Conditions | Source | Label |
|---|---|---|---|---|---|---|
| On time with offset 8 s (viewer page in Edge) | 30 of 31 phrases arrived before due; 77% started within 1 s of their moment; p95 3.2 s late | — | 2026-11-15 | dense reel, stored voice, offset set by ear, 1 run | `SPEC.md` s.16 (Streamer Mode), [EXP-008](experiments/EXP-008-streamer-mode-first.md) | measured |
| Within 1 s, recorded voice, GPU engine | 57% | — | 2026-11-21 | dense reel, Tamil + Punjabi, tunnel, 1 run; a recorded voice at natural pace is late on this reel | `SPEC.md` s.21 | measured |
| Phrases in the recorded voice | 162 of 162 | — | 2026-11-21 | as above | `SPEC.md` s.21 | measured |

### Studio

| Metric | Value | Target | Date | Conditions | Source | Label |
|---|---|---|---|---|---|---|
| Words heard back, standard (corrected rule) | 90.6% (88.4-93.0) | — | 2026-11-25 | 3 test videos, Tamil + Bengali, GPU engine, 1 job each | [EXP-027](experiments/EXP-027-hq-judge-rerun.md) | measured |
| Words heard back, HQ (corrected rule) | 95.9% (93.3-98.1) | 96%: **not reached** | 2026-11-25 | as above; two of three HQ dubs were of a damaged transcript | [EXP-027](experiments/EXP-027-hq-judge-rerun.md) | measured |
| Words heard back, HQ + all text flags (intact transcripts) | 94.5% (93.2-96.5) | 96%: not reached | 2026-11-25 | as above | [EXP-027](experiments/EXP-027-hq-judge-rerun.md) | measured |
| Words heard back, 23 Nov output, old rule -> corrected rule | standard 89.2% -> 91.1%; HQ 92.5% -> 95.5% | 96% | 2026-11-23 (re-scored 2026-11-25) | same jobs, re-scored from stored hearings | [EXP-021](experiments/EXP-021-studio-hq-vs-standard.md), [EXP-027](experiments/EXP-027-hq-judge-rerun.md) | measured |
| Turnaround, 50 s video into 2 languages | standard 81 / 54 / 66 s; HQ 133 / 117 / 136 s; HQ + flags 140 / 129 / 130 s | — | 2026-11-25 | 3 videos, nothing cached, GPU engine, laptop + tunnel | [EXP-027](experiments/EXP-027-hq-judge-rerun.md) | measured |
| Turnaround, dense 24.9 s reel | hosted 88 s; all-GPU 43-68 s | — | 2026-11-21 | Tamil + Bengali (all-GPU: 2 or 3 languages), recorded voice | `SPEC.md` s.21 | measured |
| Turnaround, dense 24.9 s reel into 4 languages | 84.9 s | — | 2026-11-13 | hosted, nothing cached, 1 job | pitch PDF (15 Nov) p.1; `logs/jobs/index.csv` | measured |
| HQ voice stage: adaptive vs 5 fixed takes | 206 s vs 524 s (61% less), same take kept on 76 of 76 lines | — | 2026-11-25 | 3 videos | [EXP-027](experiments/EXP-027-hq-judge-rerun.md) | measured |
| Largest speed-up in HQ | 1.15x | at most 1.15x (reached on videos that hardly needed it) | 2026-11-23 | 3 videos | [EXP-021](experiments/EXP-021-studio-hq-vs-standard.md) | measured |

### Engines and models

| Metric | Value | Target | Date | Conditions | Source | Label |
|---|---|---|---|---|---|---|
| Hard-audio key words, hosted Prisma | 71.3 of 80 (71-72); clean 77 | 73 of 80: not reached (1-2 short) | 2026-11-23 | 24 lines, 80 key words, hard = 15% faster + echo + noise 10 dB under, 3 runs | [EVAL_REPORT.md](../v1/EVAL_REPORT.md) s.3, [EXP-018](experiments/EXP-018-prisma-vs-whisper-hard-audio.md) | measured |
| Hard-audio key words, our Whisper | 52 of 80 (50-55); clean 70 | 73 of 80 | 2026-11-23 | as above | [EVAL_REPORT.md](../v1/EVAL_REPORT.md) s.3 | measured |
| Hard-audio key words, first measurement | hosted 73, ours 49 of 80 (clean 77 / 70) | — | 2026-11-21 | test voices are the hosted provider's own stock voices, 1 run | `SPEC.md` s.21 | measured |
| Voice engine time per line (IndicF5) | 0.79 s from the laptop (engine 0.44 + encode 0.03 + network 0.32); 3 lines at once 0.97 s | — | 2026-11-21 | A100, 12 steps, MP3 transport | `SPEC.md` s.17, [EXP-010](experiments/EXP-010-voice-engine-speedup.md) | measured |
| Voice step per phrase in Live | 0.77 s | — | 2026-11-21 | dense reel, Tamil + Bengali, 1 run | `SPEC.md` s.17 | measured |
| Separation (Demucs), 60 s of audio | 4.0-4.8 s on the A100 (replacement machine); 11.5-13.8 s on the first machine through the tunnel (15 Nov); 40.3 s on the laptop CPU | — | 2026-11-20 (GPU), 2026-11-13 (CPU) | htdemucs | `SPEC.md` s.16-17, [EXP-002](experiments/EXP-002-separation-cpu-vs-gpu.md) | measured |
| Speaker comparison on CPU (QA server) | 765 ms (727-797) for two 7 s clips | — | 2026-11-25 | laptop CPU, 4 threads, 20 comparisons | [EXP-029](experiments/EXP-029-qa-speaker-cpu.md) | measured |

### Real streams

| Metric | Value | Target | Date | Conditions | Source | Label |
|---|---|---|---|---|---|---|
| 67-min stream: first audio p50 / p95 | 2.5 s / 5.1 s | — | 2026-11-21 | user's YouTube quiz class, Punjabi heard, all-GPU, laptop + tunnel, 1363 phrases | `SPEC.md` s.21, [EXP-016](experiments/EXP-016-real-stream-67min.md) | measured |
| 67-min stream: within 0.25 / 1 / 2 s | 81% / 97% / 98% | 1 s: 90% | 2026-11-21 | as above | as above | measured |
| 67-min stream: copied voice; skipped | 1281 of 1327 spoken lines; 14 skipped as too late (about 2.1 per 10 min) | skips: 1 per 10 min | 2026-11-21 | as above; the per-10-min figure is our arithmetic | as above | measured (rate: estimate) |
| 24 Nov, longest session (16.4 min): Punjabi first audio p50 / p95 | 1949 / 3142 ms | — | 2026-11-24 | v0, GPU engine, 266 Punjabi phrases, speaker talking 62% of the time | `logs/sessions/index.csv`, [EXP-022](experiments/EXP-022-real-streams-24nov.md) | measured |
| 24 Nov, longest session: Punjabi within 0.25 s / 1 s; English within 1 s | 94.7% / 97.7%; 97.9% (100 lines, 91% copied) | 1 s: 90% | 2026-11-24 | as above | as above | measured |
| 24 Nov, all sessions: within 1 s weighted by phrases | v0 87.2% (13 sessions); v1 91.3% (4 sessions) | 90% | 2026-11-24 | different sessions and material; not an A/B | [EXP-022](experiments/EXP-022-real-streams-24nov.md) | measured |

### Costs (stand-in prices)

All from `pitch/BharatDub_Architecture_Costs_Questions.pdf` (15 Nov 2026), in rupees ($1 = 88 assumed there). The
hosted speech provider publishes no prices, so another vendor's published rates stand in. The GPU rental price is
an estimate. **None of these is a measured cost.** Volumes behind them are for nonstop speech.

| Metric | Value | Date | Conditions | Source | Label |
|---|---|---|---|---|---|
| Studio, AI cost per minute of video per language | 2 to 4.50 | 2026-11-15 | hosted path | pitch PDF B2 | stand-in |
| Live (stock voices), AI cost per hour | 196 to 322 (1 language); 530 to 910 (3 languages) | 2026-11-15 | nonstop speech | pitch PDF B3 | stand-in |
| Streamer (own voice on our GPU), AI cost per hour | about 256 (3 languages on one A100) | 2026-11-15 | A100 at $1.20 an hour (estimate) | pitch PDF B4 | stand-in |
| A100 rental | $1.20 an hour = 106 an hour | 2026-11-15 | market range $0.68-1.60 | pitch PDF B1 | estimate |
| Suggested Studio price | 15 per language-minute | 2026-11-15 | proposal | pitch PDF B2 | target |

v1 shows no cost per minute: no rate is set ([SUMMARY.md](../v1/SUMMARY.md) s.1; approval checklist "prices").

## Trends over time

### Live first audio p50

Not all points are the same measure or material; read the conditions.

| Date | Value | Conditions | Source |
|---|---|---|---|
| 2026-11-13 | 3.6 s (p95 4.7 s) | stock voices, 3 languages, whole utterances; end of speech estimated 0.3-0.6 s too kindly | `SPEC.md` s.16, `LIVE_TEST_REPORT.md` |
| 2026-11-13 | 2.3 s (p95 3.6 s) | phrases cut from partials, stock voice | `SPEC.md` s.16 |
| 2026-11-20 | 3.1-3.2 s | copied voice on the new GPU machine after tuning | `SPEC.md` s.17 |
| 2026-11-21 (morning) | 2.7 s | faster voice engine (batched guidance, MP3) | `SPEC.md` s.17 |
| 2026-11-21 | hosted 2.8-2.9 s; GPU via tunnel 2.3 s; backend on GPU machine 1.8 s | dense reel 6 loops, Tamil + Bengali | `SPEC.md` s.21 |
| 2026-11-21 | 2.5 s | real 67-min stream | [EXP-016](experiments/EXP-016-real-stream-67min.md) |
| 2026-11-23 | 2.34 s (2.27-2.40) | v1 flags off, 3 loops, Tamil + Bengali, 3 runs | [EXP-020](experiments/EXP-020-v1-live-flags.md) |
| 2026-11-24 | 2408 ms (2308-2496) | flags off, 8 loops, Punjabi + Tamil, 5 runs | [EXP-024](experiments/EXP-024-dense-speech-budget.md) |
| 2026-11-24 | 1949 ms | real session, 16.4 min, Punjabi | [EXP-022](experiments/EXP-022-real-streams-24nov.md) |
| 2026-11-25 | 2.3 s | 1 recorded session, Punjabi, budget on, 3 loops | [EXP-028](experiments/EXP-028-pitch-recording.md) |

### Live within 1 s of the video moment

| Date | Value | Conditions | Source |
|---|---|---|---|
| 2026-11-15 | 77% | Streamer Mode, offset 8 s, browser | [EXP-008](experiments/EXP-008-streamer-mode-first.md) |
| 2026-11-21 | Tamil 66% -> 86%, Bengali 78% -> 94% | stamp fix off -> on, six loops, 1 run each | `SPEC.md` s.20, [EXP-011](experiments/EXP-011-sync-stamps-and-hold.md) |
| 2026-11-21 | hosted 87%; GPU via tunnel 96%; GPU machine 93% | dense reel 6 loops | `SPEC.md` s.21 |
| 2026-11-21 (late) | 95% -> 72% | GPU engine, our speech-to-text first -> hosted speech-to-text first (`3a20c06`), Tamil + Punjabi, 1 run each | `SPEC.md` s.21 |
| 2026-11-21 | 97% | real 67-min stream | [EXP-016](experiments/EXP-016-real-stream-67min.md) |
| 2026-11-23 | 83.3% (81.2-85.0) | v1 flags off, 3 runs | [EXP-020](experiments/EXP-020-v1-live-flags.md) |
| 2026-11-24 | 86.5% off; 92.3% budget | 8 loops, 5 runs each | [EXP-024](experiments/EXP-024-dense-speech-budget.md) |
| 2026-11-24 | 97.7% | real session, 16.4 min, Punjabi | [EXP-022](experiments/EXP-022-real-streams-24nov.md) |
| 2026-11-25 | 97.1% | 1 recorded session, budget on | [EXP-028](experiments/EXP-028-pitch-recording.md) |

### Voice step per phrase (copied voice, translation to first audio)

| Date | Value | Conditions | Source |
|---|---|---|---|
| 2026-11-14 | 1.2-1.7 s a line from the laptop | first GPU machine (Seoul), 3 processes | `SPEC.md` s.16 |
| 2026-11-20 | 1.85 s (first machine had 1.45 s) | replacement machine before tuning | `SPEC.md` s.17 |
| 2026-11-20 | 1.2-1.3 s | after tuning (letters not bytes, 10 steps) | `SPEC.md` s.17 |
| 2026-11-21 | 0.77 s | batched guidance, MP3, 12 steps | `SPEC.md` s.17, [EXP-010](experiments/EXP-010-voice-engine-speedup.md) |

### Studio HQ words heard back

| Date | Value | Conditions | Source |
|---|---|---|---|
| 2026-11-23 | 92.9% (standard 93.4%) | video A only, phase 7, old rule | [EXP-021](experiments/EXP-021-studio-hq-vs-standard.md) |
| 2026-11-23 | 92.5% (standard 89.2%) | 3 videos, old rule as reported | [EXP-021](experiments/EXP-021-studio-hq-vs-standard.md) |
| 2026-11-23 | 95.5% (standard 91.1%) | same output, corrected rule (re-scored 25 Nov) | [EXP-027](experiments/EXP-027-hq-judge-rerun.md) |
| 2026-11-25 | 95.9% (standard 90.6%); all flags 94.5% | rerun, corrected rule | [EXP-027](experiments/EXP-027-hq-judge-rerun.md) |

## From the logs

The three blocks below are computed from the CSVs in the repository. Dates in `logs/` are UTC: work done in the
early morning of 23 and 25 Nov (India time) shows as 22 and 24 Nov. Versions `ws1-*`, `ws2-*`, `ws3-*`, `ws4-*`
are comparison backends of the v1.1 workstreams, not product versions.

### Live sessions by version and date

<!-- generated:start results-live-sessions -->
Generated by scripts/docs/gen_docs.py; do not edit by hand.

| Version | Date | Sessions | Session-languages | Phrases | First audio p50 (median of rows, ms) | Within 1 s (median of rows, %) |
|---|---|---|---|---|---|---|
| v0 | 2026-11-13 | 40 | 73 | 1824 | 4089 | — |
| v0 | 2026-11-14 | 40 | 57 | 1445 | 3811 | 62.9 |
| v0 | 2026-11-15 | 10 | 22 | 255 | 4319 | 71.1 |
| v0 | 2026-11-20 | 9 | 18 | 425 | 3357 | 79.7 |
| v0 | 2026-11-21 | 18 | 34 | 3536 | 2609 | 90.9 |
| v0 | 2026-11-22 | 6 | 12 | 118 | 2815 | 77.5 |
| v1 | 2026-11-22 | 4 | 8 | 188 | 2412 | 83.6 |
| v0 | 2026-11-24 | 13 | 21 | 692 | 2735 | 81.1 |
| v1 | 2026-11-24 | 4 | 6 | 203 | 2108 | 97.8 |
| ws1-budget | 2026-11-24 | 5 | 10 | 925 | 2597 | 92.6 |
| ws1-ctl | 2026-11-24 | 8 | 16 | 1493 | 2662 | 91.4 |
| ws1-native | 2026-11-24 | 6 | 12 | 985 | 2662 | 92.0 |
| ws1-off | 2026-11-24 | 5 | 10 | 926 | 2384 | 87.5 |
| ws1-tight | 2026-11-24 | 3 | 6 | 569 | 2690 | 92.4 |
| ws2-en-copy | 2026-11-24 | 3 | 6 | 503 | 2631 | 89.0 |
| ws2-en-off | 2026-11-24 | 3 | 6 | 488 | 2568 | 92.4 |
| ws2-en-stock | 2026-11-24 | 3 | 6 | 447 | 2440 | 90.9 |
| ws2-off | 2026-11-24 | 11 | 22 | 618 | 2555 | 95.8 |
| ws2-warm | 2026-11-24 | 5 | 10 | 260 | 2625 | 97.9 |
| ws2-warm2 | 2026-11-24 | 5 | 10 | 246 | 2724 | 95.8 |
| ws4-pitch | 2026-11-24 | 1 | 1 | 36 | 2387 | 97.1 |
<!-- generated:end results-live-sessions -->

Sessions = distinct sessions; session-languages = rows of `logs/sessions/index.csv`; phrases = sum of `spoken`;
medians are over rows, empty cells ignored.

### Studio jobs by version and date

<!-- generated:start results-studio-jobs -->
Generated by scripts/docs/gen_docs.py; do not edit by hand.

| Version | Date | Jobs | Median total (s) |
|---|---|---|---|
| v0 | 2026-11-13 | 6 | 30.2 |
| v0 | 2026-11-15 | 1 | 32.7 |
| v0 | 2026-11-20 | 2 | 66.1 |
| v0 | 2026-11-21 | 2 | 15.4 |
| v0 | 2026-11-22 | 1 | 33.9 |
| v1 | 2026-11-22 | 7 | 91.9 |
| ws3-adapt | 2026-11-24 | 3 | 86.1 |
| ws3-fixed | 2026-11-24 | 3 | 194.8 |
| ws3-hq | 2026-11-24 | 3 | 132.7 |
| ws3-new | 2026-11-24 | 3 | 129.7 |
| ws3-new-first | 2026-11-24 | 3 | 143.2 |
| ws3-std | 2026-11-24 | 3 | 65.8 |
<!-- generated:end results-studio-jobs -->

Source: `logs/jobs/index.csv`. Jobs differ in length and languages; the median mixes them.

### Eval harness (`backend/eval/results.csv`)

<!-- generated:start results-eval -->
Generated by scripts/docs/gen_docs.py; do not edit by hand.

| Area | Metric | Value | Unit | n | Note |
|---|---|---|---|---|---|
| stt | wer | — | % | 0 | not run (pass --wer) |
| studio | turnaround | — | s | 0 | no uncached finished job in the store |
| studio | slot_fit_natural | — | % | 0 | no dubbed lines in the store |
| live | first_audio_p50 | 2678 | ms | 26 | session 697ccb07, ta-IN, 0 phrases skipped |
| live | first_audio_p95 | 3558 | ms | 26 | session 697ccb07, ta-IN, 0 phrases skipped |
| live | heard_p50 | 3326 | ms | 26 | session 697ccb07, ta-IN, 0 phrases skipped |
| live | heard_p95 | 5787 | ms | 26 | session 697ccb07, ta-IN, 0 phrases skipped |
| live | first_audio_p50 | 3741 | ms | 26 | session a73f51a9, bn-IN, 0 phrases skipped |
| live | first_audio_p95 | 4721 | ms | 26 | session a73f51a9, bn-IN, 0 phrases skipped |
| live | heard_p50 | 6001 | ms | 26 | session a73f51a9, bn-IN, 0 phrases skipped |
| live | heard_p95 | 7521 | ms | 26 | session a73f51a9, bn-IN, 0 phrases skipped |
| live | first_audio_p50 | 3449 | ms | 26 | session a73f51a9, en-IN, 0 phrases skipped |
| live | first_audio_p95 | 4901 | ms | 26 | session a73f51a9, en-IN, 0 phrases skipped |
| live | heard_p50 | 3842 | ms | 26 | session a73f51a9, en-IN, 0 phrases skipped |
| live | heard_p95 | 5472 | ms | 26 | session a73f51a9, en-IN, 0 phrases skipped |
| live | first_audio_p50 | 3449 | ms | 26 | session a73f51a9, ta-IN, 0 phrases skipped |
| live | first_audio_p95 | 5028 | ms | 26 | session a73f51a9, ta-IN, 0 phrases skipped |
| live | heard_p50 | 4345 | ms | 26 | session a73f51a9, ta-IN, 0 phrases skipped |
| live | heard_p95 | 5767 | ms | 26 | session a73f51a9, ta-IN, 0 phrases skipped |
| live | first_audio_p50 | 2572 | ms | 35 | session c67ae2e3, ta-IN, 3 phrases skipped |
| live | first_audio_p95 | 3478 | ms | 35 | session c67ae2e3, ta-IN, 3 phrases skipped |
| live | heard_p50 | 3535 | ms | 35 | session c67ae2e3, ta-IN, 3 phrases skipped |
| live | heard_p95 | 6722 | ms | 35 | session c67ae2e3, ta-IN, 3 phrases skipped |
| live | first_audio_p50 | 2875 | ms | 33 | session 07d62a62, bn-IN, 2 phrases skipped |
| live | first_audio_p95 | 3804 | ms | 33 | session 07d62a62, bn-IN, 2 phrases skipped |
| live | heard_p50 | 4373 | ms | 33 | session 07d62a62, bn-IN, 2 phrases skipped |
| live | heard_p95 | 6350 | ms | 33 | session 07d62a62, bn-IN, 2 phrases skipped |
| live | first_audio_p50 | 3029 | ms | 33 | session 07d62a62, ta-IN, 2 phrases skipped |
| live | first_audio_p95 | 3624 | ms | 33 | session 07d62a62, ta-IN, 2 phrases skipped |
| live | heard_p50 | 4720.0 | ms | 33 | session 07d62a62, ta-IN, 2 phrases skipped |
| live | heard_p95 | 6215 | ms | 33 | session 07d62a62, ta-IN, 2 phrases skipped |
| live | first_audio_p50 | 2996 | ms | 31 | session ab0e9908, ta-IN, 4 phrases skipped |
| live | first_audio_p95 | 3751 | ms | 31 | session ab0e9908, ta-IN, 4 phrases skipped |
| live | heard_p50 | 6450 | ms | 31 | session ab0e9908, ta-IN, 4 phrases skipped |
| live | heard_p95 | 8701 | ms | 31 | session ab0e9908, ta-IN, 4 phrases skipped |
<!-- generated:end results-eval -->

Written by `backend/eval/run.py`; the file was last changed in `8d82653` (2026-11-15). Its Live rows are single
stored sessions of 13-14 Nov (UTC; hosted engine), not the numbers above. WER on ground-truth clips was never run.
