# Pitch facts

Numbers that are safe to say to an investor about Bharat Dub, and the ones that are not. Written 2026-11-25.
Every number here is **measured** unless it says otherwise, and each one must be said **with its condition**.
If a number is not on this page, do not say it. The full scoreboard is [RESULTS.md](RESULTS.md).

Three sentences that go with every Live number:

1. "Measured on a dense 24.9-second Hindi reel replayed at real-time speed" (unless the row says real stream).
2. "With our backend on a laptop and the GPU reached over a tunnel" (the setup today).
3. "Two equal runs differ by about 10 points in timing", so we quote means of several runs where we have them.

## Safe to say

| # | Claim (say it this way) | Number | Source, date | Conditions | Caveat |
|---|---|---|---|---|---|
| 1 | "The dub starts about 2.4 seconds after a phrase ends, at the median." | first audio p50 2408 ms (2308-2496), p95 3924 ms | [EXP-024](experiments/EXP-024-dense-speech-budget.md), [LIVE_DENSE_REPORT.md](../v1/LIVE_DENSE_REPORT.md) s.4, 2026-11-24 | dense reel played 8 times (speaker talking 89% of the time), Punjabi + Tamil, GPU engine, voice learned from the stream, 5 runs, flags off | Replay, not a person at a microphone. With the duration budget on the median is 2627 ms. |
| 2 | "On nonstop speech, 92% of dubbed phrases start within one second of the moment they were spoken in the video." | within 1 s 92.3% (89.8-96.1) | [EXP-024](experiments/EXP-024-dense-speech-budget.md), 2026-11-24 | as row 1, `V1_LIVE_BUDGET` on, 5 runs | v1 flag, measured on the laptop, not yet on the VM. Within 0.25 s it is 80.6%. Tamil loses content in about a third of lines read with this flag. |
| 3 | "On a real 67-minute class stream, 97% of phrases started within a second of their moment, and 96.5% of spoken lines (1281 of 1327) were in the speaker's own copied voice." | within 1 s 97%; 1281 of 1327 spoken lines copied; first audio p50 2.5 s, p95 5.1 s | `SPEC.md` s.21, [EXP-016](experiments/EXP-016-real-stream-67min.md), 2026-11-21 | our own session on a YouTube quiz class, one viewer language (Punjabi), all-GPU mode, laptop + tunnel | One stream, one language, one speaker. 14 lines skipped as too late; 7% of lines took over 4.5 s. Speech-to-text then misheard subject words. |
| 4 | "On a real 16-minute session, 98% of Punjabi phrases started within a second of their moment." | within 1 s 97.7%, within 0.25 s 94.7%, first audio p50 1949 ms, 266 phrases | `logs/sessions/index.csv`, [EXP-022](experiments/EXP-022-real-streams-24nov.md), 2026-11-24 | v0, GPU engine, voice learned from the stream, speaker talking 62% of the time | One session. Whether outside viewers watched a live broadcast is not recorded (unconfirmed). A denser session the same day had 84.8%. |
| 5 | "On our own GPU, the copied voice keeps up with live speech: 31 of 32 phrases in the speaker's voice, against 5 of 21 with a hosted voice-copy service." | 31 of 32 vs 5 of 21 | `SPEC.md` s.16, [EXP-007](experiments/EXP-007-copied-voice-hosted-vs-gpu.md), 2026-11-14 | dense reel, sync mode, Tamil, voice learned from the stream, 3 loops | One run each. Says nothing about how close the voice sounds (see "Do not claim"). |
| 6 | "A streamer records their voice once and is dubbed in it from the first phrase." | 33 of 33 spoken phrases in the streamer's voice in each of two languages | `SPEC.md` s.16 (Streamer Mode), [EXP-008](experiments/EXP-008-streamer-mode-first.md), 2026-11-15 | dense reel, Tamil + Bengali, sync mode | One run. Not tested with a real microphone, a real OBS broadcast or a phone. |
| 7 | "If the GPU link drops, the stream keeps its dub in a stock voice and gets the speaker's voice back within seconds." | 50 s stall: all of 23-24 phrases dubbed (flags on, 3 runs) vs 4 of 22 (off); copied voice back 5.6 s after the link | [EXP-023](experiments/EXP-023-link-stalls-breaker.md), 2026-11-24 | stall simulated with a local relay, dense reel, Tamil | v1 flags, off by default; "back in 5.6 s" is 1 run. Not tested on a real tunnel drop. |
| 8 | "Studio keeps the music and dubs in the creator's copied voice; machine checks hear back about 94-95% of the dubbed words." | words heard back 94.5% (93.2-96.5), HQ with review; standard 90.6% | [EXP-027](experiments/EXP-027-hq-judge-rerun.md), 2026-11-25 | three 50 s test videos (speech made by stock voices), Tamil + Bengali, one job per video | A speech-to-text check, not listeners and not translation quality. Target 96% not reached. |
| 9 | "A 50-second video comes back in two languages in about two minutes in our high-quality mode, about one minute in standard." | HQ 117-136 s; standard 54-81 s | [EXP-027](experiments/EXP-027-hq-judge-rerun.md), 2026-11-25 | 3 videos, nothing cached, GPU engine, laptop + tunnel | One job per video. |
| 10 | "Separating voice from music takes 4-5 seconds per minute of audio on our GPU, against 40 seconds on a laptop CPU." | 4.0-4.8 s vs 40.3 s per 60 s | `SPEC.md` s.16-17, [EXP-002](experiments/EXP-002-separation-cpu-vs-gpu.md), 2026-11-20 / 2026-11-13 | htdemucs, A100 40 GB | Machine-dependent; few runs. |
| 11 | "One A100 carried one stream in three languages at 19% average use." | 19% average, 100% peaks, 110 W | `SPEC.md` s.17, [EXP-010](experiments/EXP-010-voice-engine-speedup.md), 2026-11-21 | voice engines only, lines sent as a live session sends them | Not a capacity claim: two streams at once through the tunnel measured clearly worse (first audio p50 3.2 s, 56% within 1 s). |
| 12 | "All ten Indian languages of the product are selectable; each was checked once on real APIs." | 10 languages | `SPEC.md` s.16, 2026-11-13 | one line each for the five added languages | Source language is Hindi/Hinglish only. Checked once, not measured at scale. |

## Do not claim

Each item below has been said, or could be said, and is not supported. Do not say it, not even as "about".

| Do not claim | Why |
|---|---|
| "Sub-second latency" / "real-time with no delay" | No measured first audio is under 1.8 s at the median; the viewer's video is held 6 s in sync mode. |
| "1.8 seconds first audio" as our product number | Measured once, on v0, with the backend running on the GPU machine and no hosted key (`SPEC.md` s.21). The product runs on a laptop through a tunnel (2.3-2.6 s). Moving v1 to the VM is not done. |
| "90% on time" without saying "within 1 second" | Within 0.25 s, which v1 calls "on time", is 63.5-83.1% on the dense reel. |
| "96% Studio quality" / "96% accuracy" | 96% words heard back was the target and was **not reached** (95.9% best, with damaged transcripts in two of three jobs; 94.5% with intact ones). Words heard back is not accuracy, not translation quality. |
| HQ "95.9%" without the transcript caveat | Two of the three HQ dubs behind it said a damaged transcript ([EXP-027](experiments/EXP-027-hq-judge-rerun.md)). |
| Any cost per minute or per hour as a real cost; any margin | All cost figures (pitch PDF, 15 Nov) use **stand-in** prices from another vendor and an estimated GPU price; nonstop-speech volumes. No real cost per minute has been measured. |
| "Sounds like you" / voice likeness / "indistinguishable" | Never measured by listeners. No blind listening test has run (no pairs, no ratings). |
| Speaker-similarity numbers (0.63-0.76, 0.86-0.89) | They come from ECAPA2, a non-commercial (CC-BY-NC-4.0) model, and do not carry over to the model the product uses ([EXP-012](experiments/EXP-012-clone-similarity.md), [EXP-029](experiments/EXP-029-qa-speaker-cpu.md)). |
| "Works on phones" / "works with OBS to YouTube" / "works for a normal-paced streamer at a microphone" | None tested: no phone, no real OBS broadcast with this flow, no person at a microphone over a long session, no normal-paced speaker measured in Streamer Mode. |
| v1 numbers as product numbers | v1 runs on the laptop beside v0 and has not run on the VM ([ADR-0019](adr/0019-v1-on-laptop.md)); its flags are off by default. Say "in our next version, measured on test material". |
| v0 numbers measured with the backend on the GPU machine as what users get | Users get the laptop setup. |
| "At most one dropped phrase in ten minutes" | Target not reached in any setting (7.1-19.7 per 10 min on the dense reel). |
| "Our warm start makes the first phrases faster" | Not a proven gain (EXP-025). |
| "English in the speaker's voice on our own GPU" | Our voice engine has no English; English goes to a hosted voice. |
| "Any source language" | The source is Hindi/Hinglish only. |
| "Scales to many streams per GPU" | One GPU through the tunnel is one stream today; two at once measured worse. |
| "Translation quality is X" | Translation was read by eye on small samples by a non-native reader; never scored. |
| Word error rate | Never run on ground-truth clips (`backend/eval/results.csv`). |
| "Viewer hears the dub 3.4 s after a phrase ends" (pitch PDF, 15 Nov) | A 14 Nov measure of a different pipeline state; superseded by the numbers above. |
| Anything from a single recorded pitch session as typical (91.4% / 97.1%, EXP-028) | One run of 85 s proving the recording chain. |
