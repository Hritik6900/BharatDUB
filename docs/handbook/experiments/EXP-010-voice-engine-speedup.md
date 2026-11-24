# EXP-010: Batched guidance, MP3 transport, GPU utilisation

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** ADR-0010 ([../adr/0010-indicf5-own-gpu-voice.md](../adr/0010-indicf5-own-gpu-voice.md))

## Question

One engine kept the A100 only 39% busy in bf16. Where does a line's time go, and can it be cut without changing the
sound? How much of the GPU does one stream use?

## Hypothesis

Not recorded; implied: the time is Python overhead from two network passes per step (with and without the sample and
text); running both as one batch of two roughly halves it. Opus encoding on the machine's CPU is a second cost.

## Setup

- Model: IndicF5 DiT 337.1 M parameters + Vocos vocoder 13.6 M, bf16, A100 40 GB GPU VM (address in
  `docs/v1/NEEDS_APPROVAL.md`).
- `BatchedGuidance` (`CFG_BATCH=1`; `CFG_BATCH=0` restores the library's two passes); `bench_cfg.py` compares them.
- Transport: Opus vs MP3 (VBR, about 39 kbit/s) (`gpu_voice_format`).
- Utilisation: engines only, lines sent as a live session sends them.
- Live: the dense 24.9 s Hindi reel, sync mode, voice learned from the stream, Tamil + Bengali, one run, morning.
  Backend on the laptop, engines through the tunnel.

## Metrics

- Engine time per line at a given step count; time from the laptop; GPU busy %.
- Audio closeness: log-mel distance (dB) to the fp32 two-pass audio; fp32 agreement in dB.
- Live: **first audio**, voice step, phrases in the copied voice, **hold**, **behind**, **on time**
  ([GLOSSARY](../GLOSSARY.md)); **words heard back** (`scripts/live_quality.py`).

## Results

All **measured**, 2026-11-21 (SPEC.md section 17 "GPU engine made faster"; gpu_engine README).

| What | Before | After |
|---|---|---|
| 10 steps, one line on the GPU | 742 ms (two passes) | 366 ms (batched), GPU 52% busy |
| 12 steps | not given | 439 ms (16 steps 574 ms) |
| Encode one line | Opus 144 ms | MP3 30 ms, same size |
| One line from the laptop | 1.33 s | 0.79 s (engine 0.44 + encode 0.03 + network 0.32) |
| Three lines at once from the laptop | 1.75 s | 0.97 s |

- Sound: fp32 batched vs two-pass agree to -37..-49 dB; bf16 log-mel distance from fp32 0.4-1.2 dB (two-pass bf16
  0.5-0.6 dB). MP3 0.48 dB vs Opus 0.73 dB log-mel.
- Network: two trips of 157 ms (a 14 KB answer does not fit the first TCP window after idle). An interactive tunnel
  (TCP_NODELAY) cut a small request 359 -> 157 ms but a line not at all.

GPU use, engines only:

| Load | Average | Peak | Note |
|---|---|---|---|
| Idle | 0% | - | 13.1 of 40 GB (three engines + Demucs) |
| 1 language, a phrase every 2.2 s | 11% | 70% | |
| 3 languages | 19% | 100% | 110 W |
| 3 languages, a phrase every 1.0 s | 54% | - | line still 845 ms median, slowest 2.6 s |

Live on the faster engine, one run:

| Metric | 21 Nov | 20 Nov (EXP-009) |
|---|---|---|
| First audio p50 | 2.7 s both languages | 3.1-3.2 s |
| First audio p95 | 3.7 s Tamil / 5.3 s Bengali | 3.9 / 3.8 s |
| Voice step | 0.77 s a phrase | 1.2-1.3 s |
| In the copied voice | 30 of 32, 33 of 35 | 33 of 33, 31 of 31 |
| Hold | stayed 6 s | ended at 9 s |
| Behind p50 / p95 | 0.3-0.4 s / 2.4-2.6 s | 0.2-0.4 s / 1.8-3.5 s |
| On time (within 0.25 s) | 47% | not given |
| Words heard back, Tamil / Bengali (same-hour check) | 74% / 72% | 69% / 73% |

Hosted stock Tamil voice in the 21 Nov run: 69% heard back.

## Caveats

- One Live run; the first three Bengali phrases of the session took 5-8 s (drives the 5.3 s p95).
- Words heard back on this reel read lower than the 80-89% of earlier reports; both engines were checked in the same
  hour, so the comparison holds but the absolute level is reel-dependent.
- The hosted speech-to-text failed every request during this work and answered again at 06:13 UTC on 21 Nov (INC-02,
  [../INCIDENTS.md](../INCIDENTS.md)).

## Decision taken

`CFG_BATCH=1`, steps back at 12, `gpu_voice_format=mp3` (ADR-0010).

## Links

- [SPEC.md](../../../SPEC.md) section 17 ("GPU engine made faster")
- [gpu_engine/README.md](../../../gpu_engine/README.md) "Speed, measured 21 Nov 2026"
- Commits: `ada2272` (batched guidance, MP3), `95cb280` (Live on the faster engine)
- Related: [EXP-009](EXP-009-voice-engine-tuning.md), [EXP-013](EXP-013-steps-and-pace.md)
