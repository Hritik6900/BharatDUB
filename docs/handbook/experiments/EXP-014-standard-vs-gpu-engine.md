# EXP-014: Standard (hosted) vs GPU engine, Live/Streamer/Studio

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** ADR-0014 ([../adr/0014-two-engines-per-session.md](../adr/0014-two-engines-per-session.md))

## Question

If speech-to-text and translation also run on our GPU machine beside the voice engines (all-GPU mode), how do Live,
Streamer Mode and Studio compare with the hosted engine?

## Hypothesis

Not recorded; implied: removing the hosted round trips (about 1.0 s speech-to-text and 0.85-0.95 s translation per
line) cuts first audio and puts more phrases on time; quality should hold.

## Setup

- GPU engine: Whisper-Hindi2Hinglish-Apex (speech-to-text, decoded every 0.3 s for partials), Gemma 4 E4B on vLLM
  (translation), IndicF5 (voice); together 34.7 of 40 GB on the A100 GPU VM (address in `docs/v1/NEEDS_APPROVAL.md`).
  Hosted services as fallback.
- Hosted engine: Prisma, Gemini (`gemini-3.1-flash-lite` for Live), IndicF5 copied voice, hosted stock voices.
- Three placements: hosted; all-GPU with the backend on the laptop (tunnel); all-GPU with the backend on the GPU
  machine, no hosted key.
- Live: the dense 24.9 s Hindi reel, six loops, voice learned from the stream, Tamil + Bengali, hold 6 s. One run each
  unless said (hosted: two runs).
- Streamer: recorded voice, Tamil + Punjabi, through the tunnel. Studio: dense reel, one recorded voice with consent,
  through the tunnel.

## Metrics

- **First audio** p50 / p95, **on time** within 0.25 / 1 / 2 s, worst lateness, skipped, phrases in the copied voice,
  **words heard back** ([GLOSSARY](../GLOSSARY.md)).
- Studio: turnaround (s), words heard back, lines inside their slot.

## Results

Live, **measured**, 2026-11-21 (SPEC.md section 21):

| | Hosted (two runs) | All-GPU, backend on laptop (tunnel) | All-GPU, backend on GPU machine, no hosted key |
|---|---|---|---|
| First audio p50 / p95 | 2.8-2.9 s / 3.9-4.1 s | 2.3 s / 3.0 s | 1.8 s / 2.1 s |
| Within 0.25 s / 1 s / 2 s | 61-63% / 87% / 93-97% | 78% / 96% / 100% | 76% / 93% / 100% |
| Worst lateness | 3.3-3.7 s | 1.2 s | 1.7 s |
| Skipped | 0-1 | 6 | 0 |
| In the copied voice | 146-149 of 147-151 | 158 of 160 | 163 of 163 |
| Words heard back, Tamil / Bengali | 77-81% / 78-79% | 82% / 73% | 80% / 72% |

- GPU 36% busy on average, 100% at peaks, during the machine run. **measured**.
- Real site (port 8010) in GPU mode, one run: first audio p50 2.4 s / p95 3.4 s, 78% on time, no errors. **measured**.
- Hold on the GPU machine: 4.5 s gave 76% / 91% / 99%, same as 6 s; 4 s gave 63% / 89% / 98%. **measured**, one run
  each.

Streamer, **measured**, one run: 162 of 162 phrases in the recorded voice, words 82% Tamil / 78% Punjabi (hosted,
earlier runs 73-79% / 79-86%), first audio p50 2.8-3.0 s, 57% within 1 s (as in hosted mode).

Studio, **measured**:

| | Hosted | All-GPU |
|---|---|---|
| Turnaround | 88 s (Tamil + Bengali) | 43-68 s (two or three languages) |
| Words heard back | 76% / 74% | 91-93% (Tamil, Bengali, Punjabi) |
| English words | left in Latin letters | target script |
| Lines in slot | not given | every line |

Site check of the Engine button, one session each way, same reel: hosted path 35 of 35 source lines in Devanagari,
GPU path 42 of 42 in Latin letters (translation p50 see EXP-015). **measured**.

Found on the way: a voice sample text in Latin letters gave 61% / 72% (Bengali / Tamil) heard back vs 91% / 87% in
Devanagari; the first all-GPU run had Bengali at 43%. **measured**.

## Caveats

- One run per GPU column; Studio "one line a language" in the words column is a small sample.
- The first all-GPU Studio run put a 37.7 s Tamil line into a 24.9 s slot; fixed by asking the engine again at a higher
  speed (not under 300 ms a word, at most 1.5x).
- GPU mode is Hindi/Hinglish source only; stock voices and English stay hosted; the console source caption is Latin.
- Translation quality read by eye on 42 lines, not scored; one error seen ("an hour and a half" became two hours).
- Two streams on one GPU were not tried here (see EXP-017).

## Decision taken

Two engines chosen per session/job by an Engine button; hosted stays the default (ADR-0014). GPU path models in
ADR-0015. Default hold stays 6 s because through the tunnel audio arrives 0.5 s later.

## Links

- [SPEC.md](../../../SPEC.md) section 21 (intro, "Where the time went", the Live table, Streamer, Studio, "Found on
  the way")
- [README.md](../../../README.md) "Results", "All-GPU mode (21 Nov 2026)"
- [gpu_engine/README.md](../../../gpu_engine/README.md) "All-GPU mode"
- Commits: `cc7fd39` (all-GPU mode), `bcee6aa` (Studio in all-GPU), `4709425` (measured and documented), `31673b9`
  (engine per session/job)
- Related: [EXP-015](EXP-015-gemma-vs-gemini-latency.md), [EXP-016](EXP-016-real-stream-67min.md),
  [ADR-0013](../adr/0013-best-provider-per-capability.md), [ADR-0015](../adr/0015-gpu-stt-translation.md)
