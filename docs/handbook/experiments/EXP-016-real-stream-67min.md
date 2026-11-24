# EXP-016: Real 67-minute stream in all-GPU mode

- **Date:** 2026-11-21
- **Status:** done
- **Decision:** ADR-0011 ([../adr/0011-borrowed-a100-ssh-tunnels.md](../adr/0011-borrowed-a100-ssh-tunnels.md))

## Question

How does the all-GPU engine hold up on a real, long stream (not the dense test reel), and what breaks?

## Hypothesis

Not recorded; implied: the reel results (EXP-014) carry over to a real class stream; a long session will show failure
modes a 2-minute test cannot.

## Setup

- Source: the founder's own session on 21 Nov 2026 evening, a YouTube quiz class, 67 minutes, 1363 phrases; one viewer
  language, Punjabi. (A real 25-minute stream in the same mode came first the same day; commit `fd93754`.)
- Engine: all-GPU (Whisper-Hindi2Hinglish-Apex, Gemma 4 E4B, IndicF5), backend on the laptop, engines through the SSH
  tunnel to the A100 GPU VM (address in `docs/v1/NEEDS_APPROVAL.md`); hosted services as fallback.
- Session data from the Live pipeline's per-phrase records. One session (n = 1 stream).
- No transcripts or audio are kept in this record.

## Metrics

- **First audio** p50 / p95; **on time** within 0.25 / 1 / 2 s ([GLOSSARY](../GLOSSARY.md)).
- Lines in the copied voice, skipped as too late, lines over 4.5 s.
- Speech-to-text speed: end of phrase to text, p50 / p95.

## Results

All **measured**, 2026-11-21, one stream (SPEC.md section 21 "A real stream in this mode").

| Metric | Result |
|---|---|
| Phrases | 1363 |
| First audio p50 / p95 | 2.5 s / 5.1 s |
| Within 0.25 / 1 / 2 s of the moment | 81% / 97% / 98% |
| Spoken lines in the copied voice | 1281 of 1327 |
| Skipped as too late | 14 |
| Lines over 4.5 s | 94 (7%) |
| Speech-to-text, end of phrase to text, GPU engine | p50 0.69-0.72 s, p95 1.7-1.9 s (556 lines) |
| Speech-to-text, hosted (while on fallback (unconfirmed)) | p50 0.77 s, p95 1.8 s (272 lines) |

Every bad stretch sat on a stall of the laptop-to-machine link; the machine answered in 2 ms and ping was fine
meanwhile (INC-04, [../INCIDENTS.md](../INCIDENTS.md)).

Found and fixed (counts **measured** on this stream or the 25-minute one):

| Problem | Count | Fix |
|---|---|---|
| After a tunnel drop the session stayed on hosted speech-to-text until that socket's 15-minute cap | - | engine asked every 15 s, hosted stream ends at the next final (`stt_gpu.RETURN_CHECK_S`) |
| A phrase cut one word before its sentence ended | 19 of 490 phrases | cutter looks at the unsettled next word |
| A tail repeated the words just dubbed (hosted path) | 4 of 270 lines | tail no longer starts with them |
| "nan" written for non-speech | 9 of 1000 lines (one spoken) | dropped in engine and provider, also at line start |
| Sessions from 13-15 Nov still marked "live" | 5 | closed at server start |
| Engine VAD CPU use for one stream | 1.3 cores | one torch thread (0.2 cores idle-measured) |
| One SSH connection for all engines: one stalled packet held all | - | `tunnel.ps1` opens one connection per kind of traffic |

After the fixes, one check run on the site: no errors, no one-word lines, no "nan", first audio p50 2.4 s.
**measured**, one run.

## Caveats

- One stream, one viewer language, one speaker; the founder was the streamer.
- Open after this stream: the hold grew from 6 s to 11 s during the stalls and never came back down; 47 genuine one- or
  two-word lines were dubbed as lines of their own; the health panel asks engines one after another and hangs when the
  link is slow.
- The same night a second test run beside this stream on the one GPU and tunnel dropped the stream to first audio p50
  3.2 s and 56% within 1 s (EXP-017).

## Decision taken

One SSH tunnel per kind of traffic; return to the GPU speech-to-text after a drop (ADR-0011). The hold not coming back
down was left open.

## Links

- [SPEC.md](../../../SPEC.md) section 21 ("A real stream in this mode")
- Commits: `fd93754` (25-minute stream fixes), `809ed4a` (stale "live" sessions closed), `93b5c45` (tail repeat),
  `f6d4c50` and `ff3a162` ("nan", VAD thread), `9fae6c8` (tunnel per traffic)
- Related: [EXP-014](EXP-014-standard-vs-gpu-engine.md), [EXP-017](EXP-017-indic-mio-vs-indicf5.md),
  [ADR-0014](../adr/0014-two-engines-per-session.md)
