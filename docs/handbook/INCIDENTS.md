# Incidents

Postmortems, blameless, dated 2026-11-25. Times are as the source gives them (UTC or the laptop's local time, said
each time). Numbers are **measured** unless labelled. Sources: SPEC sections 17, 20 and 21;
`logs/streams/events.log`; `docs/v1/PROGRESS.md` (v1.1 WS0, WS2, WS3); `docs/v1/V1_1_SUMMARY.md`;
`docs/v1/NEEDS_APPROVAL.md`. Item numbers below are NEEDS_APPROVAL's current numbers.

| Id | Date | What | Kind |
|---|---|---|---|
| INC-01 | 15 Nov 2026 | Wrong PC clock stopped every hosted call | outage (Live) |
| INC-02 | 21 Nov 2026 | Hosted speech-to-text failed every request | provider outage |
| INC-03 | 21 Nov 2026 | Stale voice profile text written back by the server | data |
| INC-04 | 21 Nov 2026 | Tunnel stalls on a real 67-minute stream | degraded Live |
| INC-05 | 24 Nov 2026 | Three link stalls: the laptop in standby | outage |
| INC-06 | 25 Nov 2026 | Hosted stock voice refusing lines (HTTP 502) | provider degradation |
| INC-07 | 25 Nov 2026 | Studio HQ transcript damage found | quality (silent) |

## INC-01 Wrong PC clock

- **Date:** 15 Nov 2026 (SPEC section 17). Exact hours: unconfirmed.
- **Impact:** Live produced 0 phrases and no dub: every connection to the hosted provider failed with "certificate
  is not yet valid".
- **Timeline:**
  - The night before, the hosted provider renewed its TLS certificate.
  - The dev laptop's clock was 5 h 30 min behind, so the new certificate looked "not yet valid".
  - The fault looked like a pipeline failure until the clock was compared with a server.
  - Fixed on 15 Nov: the console names a wrong clock instead of a raw certificate error (`10bd8e1` / `89b68e4`).
- **Root cause:** the laptop's clock. That the offset equals India's offset from UTC suggests a time-zone or
  time-sync setting (unconfirmed).
- **Fix:** clock synced; the console now says "sync the clock".
- **Follow-ups:** before blaming the pipeline, check `date` against a server's `Date` header (demo-day checklist,
  [RUNBOOK.md](RUNBOOK.md#demo-day-checklist)). `demo-check.sh` and `warmup.sh` do not check the clock (read
  25 Nov 2026): a candidate for the check script.

## INC-02 Hosted STT outage

- **Date:** 21 Nov 2026 (night of 20-21 Nov; start time unconfirmed). Back at **06:13 UTC on 21 Nov** (SPEC
  sections 17 and 20).
- **Impact:** hosted speech-to-text (REST and realtime) answered every request with `TRANSCRIPTION_FAILED`, even a
  clean line made by the same vendor's own voice, while its voices worked. With one speech-to-text provider and no
  fallback, Live, Studio transcription and new voice recordings all stop. It hit engine-tuning work, not a user
  session, as far as the sources say.
- **Timeline:** checked several times through one working session; answered again at 06:13 UTC.
- **Root cause:** on the provider's side; not known to us. Our side: a single speech-to-text provider, and a health
  panel that shows "key set" rather than whether the service answers.
- **Fix:** the same day, all-GPU mode (`cc7fd39`) and the engine choice per session (`31673b9`) gave a second
  speech-to-text (our Whisper on 9030); in the GPU engine each is the other's fallback for Hindi (`FallbackSTT`);
  since `3a20c06` the hosted one hears first.
- **Follow-ups:** the Standard engine still has no second speech-to-text; Whisper hears Hindi/Hinglish only.
  Health checks that call the service (v1 `/health`, `demo-check.sh`). Monitoring and alerts: SPEC section 20.
  See [ADR-0015](adr/0015-gpu-stt-translation.md), [ADR-0016](adr/0016-hosted-stt-first.md),
  [EXP-018](experiments/EXP-018-prisma-vs-whisper-hard-audio.md).

## INC-03 Stale voice profile text written back by server

- **Date:** found 21 Nov 2026 during the copied-voice similarity check (SPEC section 20). When the stale write
  happened: unconfirmed (an earlier repair).
- **Impact:** one Streamer Mode profile's stored text did not belong to its sample (text of a 15.7 s cut, file a
  9 s cut). Its lines came out at 250-300 ms a word instead of 455-555, words heard back 53-73%, voice similarity
  0.57-0.58 (ECAPA2 scale). The 20 Nov Streamer Mode numbers ("behind p50 0 s") were made while it was stale, with
  lines about twice too fast, and do not stand.
- **Timeline:** a repair script wrote the local JSON store while the backend ran; the backend held its own copy in
  memory and wrote the old text back on its next change. Found by reading lines heard back and line lengths.
- **Root cause:** `LocalStore` is one process, one file, held in memory and written on every change; a second
  writer is overwritten.
- **Fix:** `voice_ref.sample_text` checks the stored length against the file wherever a stored voice is sent to
  the engines, transcribes the file again when they differ and corrects the profile (`86188e5`). After the fix:
  words 87-98% in four languages, voice 0.63-0.70.
- **Follow-ups:** rule: never write the local store from a script while the server runs
  ([RUNBOOK.md](RUNBOOK.md#backup)). A real database (`V1_STORE=postgres`, item 14) removes the class of fault.
  See [ADR-0004](adr/0004-local-json-store.md), [EXP-012](experiments/EXP-012-clone-similarity.md).

## INC-04 Tunnel stalls on the 67-min stream

- **Date:** 21 Nov 2026, evening (SPEC section 21).
- **Impact:** the founder's own stream (a YouTube quiz class, 67 minutes, 1363 phrases, Punjabi, all-GPU mode,
  backend on the laptop). Overall it was good (first audio p50 2.5 s / p95 5.1 s; 81% / 97% / 98% within 0.25 / 1 /
  2 s), but 94 lines (7%) took more than 4.5 s, 14 lines were skipped as too late, and the hold grew from 6 s to
  11 s and never came back down. Every bad stretch sat on a stall of the laptop-to-machine link while the machine
  answered in 2 ms and ping was fine.
- **Timeline (order from SPEC section 21; clock times unconfirmed):**
  - Stalls of the link held speech-to-text, translation and voice up together: all engines shared one SSH
    connection.
  - After a tunnel drop the session moved to hosted speech-to-text and stayed there until that connection's
    15-minute cap.
  - A test run was started beside the stream on the same GPU and tunnel; while both ran the stream measured first
    audio p50 3.2 s and 56% within 1 s, against 2.5 s and 80% alone afterwards.
- **Root cause:** one SSH connection carrying every kind of traffic over a link that stalls; no return path to the
  GPU speech-to-text before the hosted socket's cap; a second stream on one GPU.
- **Fix (21 Nov):** `tunnel.ps1` opens one connection per kind of traffic (`9fae6c8`); the GPU speech-to-text is
  asked every 15 s and the hosted stream ends at the next final (`stt_gpu.RETURN_CHECK_S`). Also fixed from the
  same stream: phrase cut one word early, tails repeating dubbed words, "nan" lines, stale "live" sessions closed
  at start, VAD CPU use.
- **Follow-ups:** the hold does not come back down (built 26 Nov 2026: ADR-0035, EXP-030; the viewer page's part
  still needs a browser test); one GPU
  through one tunnel is one stream (rule); backend on the VM (items 1-3); breaker + ladder (v1.1 WS0,
  [ADR-0027](adr/0027-breakers-degrade-ladder.md)); tunnel watchdog (item 17). See
  [ADR-0011](adr/0011-borrowed-a100-ssh-tunnels.md), [EXP-016](experiments/EXP-016-real-stream-67min.md).

## INC-05 Link stalls of 24 Nov

- **Date:** 24 Nov 2026. Times below are the laptop's local time from `logs/streams/events.log` and the Windows
  event log (`docs/v1/PROGRESS.md` v1.1 WS0; NEEDS_APPROVAL item 16).
- **Impact:** every service, GPU and hosted, stopped answering at once, three times: about 2 min, 3 h and 44 min.
  A sleeping PC stops the backend too, so any live session stalls. Which sessions, if any, were live during each
  stall is not stated in the sources (unconfirmed).
- **Timeline:**

  | Stream watcher: nothing answers | Windows: standby |
  |---|---|
  | 15:05:53 to 15:07:46 (`ENGINE DOWN` x8 / `ENGINE BACK`) | 15:05:18 to 15:07:04 |
  | 16:01:05 to 19:01:23 (`LINK STALL` / `LINK BACK`) | 16:01:00; sleep at 16:43:06; back at 19:00:51 |
  | 19:17:07 to 20:01:54 (`LINK STALL` / `LINK BACK`) | 19:17:03 to 20:01:13 |

- **Root cause:** the laptop entered Modern Standby, "S0 Low Power Idle, Network Disconnected": in standby the
  network is off. Settings read on 24 Nov: lid closed on AC = Sleep; sleep after 180 min idle on AC. The watcher's
  own lines already showed it: the hosted services were among the 8 that did not answer, so it was not the tunnel.
- **Fix:** none applied yet to the power settings (they are the founder's: item 16, three `powercfg` lines). For
  stalls an awake PC does have, v1.1 WS0 built circuit breakers and the Live degrade ladder (`2cad302`): in a 50 s
  relay-made stall 4 of 22 phrases were dubbed with the flags off (1 run), all with them on (3 runs).
- **Follow-ups:** item 16 (sleep off on AC), item 17 (tunnel watchdog), item 2 (backend on the VM: the backend
  then no longer sleeps with the laptop, though the browser sound still comes from it). See
  [ADR-0019](adr/0019-v1-on-laptop.md), [ADR-0027](adr/0027-breakers-degrade-ladder.md),
  [EXP-023](experiments/EXP-023-link-stalls-breaker.md).

## INC-06 Hosted stock voice refusing lines, HTTP 502

- **Date:** night of 24-25 Nov 2026, measured about 00:36 to 01:15 IST on 25 Nov (`docs/v1/PROGRESS.md` v1.1 WS2).
- **Impact:** the hosted stock voice answered many lines with HTTP 502 "We are facing technical difficulties" within
  0.2 s: 5 of 18 single lines asked outside any session, and 59% of English stock lines at the first try in the
  sessions. With `V1_EN_VOICE=stock` 42% of English lines had no audio even after one retry (the second try was
  refused 71% of the time). The hosted copy of the voice answered every line (119 of 119). It hit measurement runs
  (comparison backends), not a user stream; on the founder's stream of 24 Nov no line was refused.
- **Timeline:** the opening stock lines of an earlier WS2 batch were silent with no error recorded; an hour later the
  refusals were seen directly; the English measurement ran through them.
- **Root cause:** on the provider's side; not known to us. Our side: the streamed hosted voice has no retry, so a
  refused line is silently without audio (flags off, v0 behaviour).
- **Fix:** with `V1_EN_SINGLE_VOICE` a refused English line is asked once more (brought back 16 of 55 refused lines
  a run, 29%). `V1_EN_VOICE=copy` keeps English audible on such a night.
- **Follow-ups:** item 22 (b): should a session in the stock voice move once to the copy when the stock voice stops
  answering (founder's decision). The stock column's timing that night is flattered; a healthy night was not
  measured (item 19 c). See [ADR-0031](adr/0031-english-single-voice.md),
  [EXP-026](experiments/EXP-026-english-voice-mix.md).

## INC-07 HQ transcript damage found

- **Date:** found 25 Nov 2026 (v1.1 WS3); the damage was already in the 23 Nov HQ jobs.
- **Impact:** in Studio HQ without `V1_HQ_REVIEW`, the "merge the hearings" and "clean" steps changed what the video
  says in two of three test videos: 25 of 38 lines no longer the line heard. In one video 12 of 13 lines held the
  line before them (the last line never said); in another all 13 lines came back in Latin letters, three without
  their first words. The heard-back score could not see it (93.3% and 98.1% on those videos). The 23 Nov HQ figure
  (92.5%) was partly made from damaged transcripts. Test videos only; no user job is known to be affected
  (unconfirmed).
- **Timeline:** found by reading the stored first hearing (`src_text_raw`) against the line after merge and clean,
  while correcting the judge's counting rule.
- **Root cause:** the merge prompt gives each line with its neighbours as context and the model answered with the
  line before; our Whisper's Latin-letter hearing was merged in; heard-back compares the dub with its own text, not
  with what was said.
- **Fix:** `V1_HQ_REVIEW` puts a cleaned line back when it is no longer the line heard (every English term kept,
  the script kept, at most four words in ten gone): 0 such lines with it. `93b5e75`. Recommended: HQ only together
  with `V1_HQ_REVIEW` and `V1_HQ_JUDGE`.
- **Follow-ups:** decide whether HQ may be offered without the review and whether the second hearing by our
  Whisper is worth keeping ([OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)); labels on `/studio/calibrate` (item 21) to tie
  the score to a listener. See [ADR-0030](adr/0030-hq-judge-and-review.md),
  [EXP-027](experiments/EXP-027-hq-judge-rerun.md).
