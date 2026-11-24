# Glossary

Terms used across the handbook, the v1 reports and the logs. Dated 2026-11-25. Headings are lowercase so that
links such as `GLOSSARY.md#on-time` work. Sources in brackets.

## Timing (Live)

### on-time
A phrase is on time when its dub starts close to the video moment its source words were spoken at. Reported at
three tolerances: **within 0.25 s**, **within 1 s**, **within 2 s**. "On time" alone means within 0.25 s
(SPEC section 20, 21 Nov 2026). Measured in sync mode from `late_ms` per phrase. See [hold](#hold), [sync mode](#sync-mode).

### first audio
Time from the end of a phrase (`t_speech_end`) to the first dubbed audio sent for it (`first_audio_ms`). Not what
a viewer hears when audio queues up: see [heard delay](#heard-delay) (`logs/README.md`; SPEC section 16).

### heard delay
Time from the end of a phrase to when a viewer starts hearing its dub (`heard_ms`; the server's estimate from a
per-language playhead). Added on 14 Nov 2026 because first audio of 2.3 s hid a heard p50 of 7.8 s (SPEC section 16).

### dur_ratio
Dubbed seconds over the seconds of the source slot (`dub_ms / slot_ms`); over 1.0 the dub is longer than the
speech it replaces. Stored per phrase from v1.1 (`logs/README.md`; `docs/v1/LIVE_DENSE_REPORT.md`).

### backlog
How far the dub queue of a language was behind the video when a phrase's turn came (`backlog_ms`, v1.1). The rate
controller (`V1_LIVE_RATECTRL`) acts on it (`logs/README.md`).

### slot
The time a dubbed line may take. Studio: from a line's start to the next line's start (last line: to the end of the
video) (SPEC section 8). Live: the span of the source phrase (`slot_ms`, v1.1).

### hold
In sync mode, how far each viewer's video is held behind the console's, so the dub can arrive before its moment.
Starts at 6 s (8.5 s with a copied voice in the first version); grows by what the dub needs, at most 1 s a step
since 21 Nov 2026 (`live_sync_grow_step_ms`), limit 15 s; it does not come back down (SPEC sections 16, 20, 21).
Also called the sync delay (`delay_ms`).

### sync mode
The console sends the YouTube player's time with the sound; every caption and audio message carries `media_s`
(the video time the phrase was spoken at); `/watch` holds its video by the [hold](#hold) and starts each phrase
when its player reaches `media_s` (SPEC section 16, 14 Nov 2026, `live_sync`).

### offset
Streamer Mode with a streamer's own mic: speech is real time and YouTube shows it later, so each phrase is due
`offset_ms` after it was spoken (console slider 0-40 s); set by ear, never grows by itself (SPEC section 16).

### tempo
Speed-up applied to fit a dubbed line (ffmpeg `atempo`). Limits: Live 1.3x (`LIVE_FIT_MAX_TEMPO`; 1.4x in dense
mode with `V1_LIVE_RATECTRL`); Studio 1.35x, 1.15x with `V1_FIT_115`. A phrase "at the speed limit" needed the
full limit (SPEC sections 8, 16; `docs/v1/RUNBOOK.md`).

### budget
A limit on the translated line's length so the dub fits its slot. v0: `live_length_budget` (word limit from the
voice's and speaker's pace, 1.15x / 0.9x / 0.6x of the speaker's time). v1.1 `V1_LIVE_BUDGET`: the phrase's own
slot as words and letters from the measured ms per word and per letter of this voice in this language; an answer
more than 15% over is asked for once more, shorter (SPEC section 16; `docs/v1/RUNBOOK.md` section 3).

### expansion model
Per language, how much longer the dub is than the source; seeds the v1.1 budget from
`backend/config/live_expansion.json` and learns from every line (`docs/v1/RUNBOOK.md` section 3).

### link stall
Every GPU endpoint failing in one health round (asked every 5 s while a session is live): the link, not one
server. With `V1_BREAKER` it opens every circuit at once. In the stream watcher, `LINK STALL` with the hosted
services in the list means the PC was asleep ([INC-05](INCIDENTS.md#inc-05-link-stalls-of-24-nov)).

## Pipeline (Live)

### phrase
The unit Live translates and dubs: 6-12 words cut at a clause boundary from the speech-to-text's stable text, or
the tail of an utterance. Each has `seq` and `t_speech_ms` (SPEC sections 9, 16).

### phraser
The code that cuts phrases (`Phraser` in `backend/app/live/assembler.py`). `V1_PHRASE_DYNAMIC`: first phrase 4-6
words, later 8-12, lines under 3 words join the next.

### partial
An interim transcript from realtime speech-to-text (`partial_transcript`, about every 0.5 s on the hosted service;
our Whisper re-decodes every 0.3 s). Its **stable text** is the part that will not change; phrases are cut only
from stable text. Our engine counts a word as settled once two decodes agree and holds the last agreed word back
(SPEC sections 16, 21).

### tail
The words of an utterance that were not yet cut into a phrase when the final transcript arrived (SPEC section 16).

## Voices and engines

### copied voice
The speaker's own voice made by a model from a sample (IndicF5 on our GPU, or the hosted clone). Needs consent.

### stock voice
A fixed hosted voice per language (Timbre v2.5), used for English, before a copied voice is ready, and as fallback.

### voice learned from the stream
A copied voice made during a Live session from about 7 s of the stream's speech, with the consent tick; ready
about 9 s in; stock voices until then (SPEC section 16).

### recorded voice
A copied voice from a streamer's one-time recording with the consent sentence read aloud; ready from the first
phrase (Streamer Mode, SPEC section 16).

### engine
Which providers a session or job uses. **Standard** (`cloud`, the default): hosted speech-to-text and translation.
**GPU** (`gpu`): our Whisper and Gemma on the A100, with the hosted ones as fallback (and the hosted speech-to-text
hearing first since `3a20c06`). Chosen by the "Engine" button (SPEC section 21).

### rung
A step of the Live degrade **ladder** (`V1_LIVE_DEGRADE`): 0 copied voice, 1 stock voice, 2 captions only (no
voice), 3 original sound (not translated). Two failures step down, one success steps up (`docs/v1/PROGRESS.md` WS0).

### breaker
A circuit breaker per GPU endpoint (`V1_BREAKER`): a timeout, or 2 failures in 10 s, opens it for 30 s; calls then
fail at once and the fallback answers.

## Quality (Studio and voice)

### words heard back
The dub is transcribed again by speech-to-text (the hosted Prisma unless said) and the share of its own words
found is the score. Also "heard-back", "back-check". It cannot see a dub of the wrong sentence
([INC-07](INCIDENTS.md#inc-07-hq-transcript-damage-found)).

### judge
The speech-to-text that hears a dubbed line back. With `V1_HQ_JUDGE`: hosted first, then our Whisper (Hindi only),
then the QA server's Whisper once it runs; each line records its judge.

### hq
Studio HQ (`V1_STUDIO_HQ`): two hearings merged, cleaned transcript, word limit per line, review, several takes per
line scored, best kept, weak lines flagged; about twice the time of a standard job (128 s against 67 s, 25 Nov
rerun, V1_1_SUMMARY).

### takes
The versions of one dubbed line made in Studio HQ. `V1_HQ_ADAPTIVE`: one take first, more (up to 5) only while the
best score is under the flag line.

### flagged line
An HQ line whose best take scored under the flag line (`V1_HQ_BACKCHECK_MIN`, 0.9 by default, not tied to a
listener yet).

### ecapa2 similarity
Cosine similarity of ECAPA2 speaker embeddings, used for the copied voice on 21 Nov 2026 (real person against
themselves 0.86-0.89, copies 0.63-0.76). ECAPA2 is non-commercial and was rejected; the QA server uses
speechbrain ECAPA-TDNN on another scale, so those numbers do not carry over ([MODELS.md](MODELS.md)).

### key words
Subject words in a test line (names, terms) counted as right or wrong in a transcript; the measure of speech-to-text
on the [hard set](#hard-set) (SPEC section 21).

## Test material

### dense reel
A 24.9 s Hindi reel of almost continuous speech, the standard Live test, replayed in loops (8 loops = 211 s, 89%
speaking share) (`docs/v1/LIVE_DENSE_REPORT.md`). It repeats 11-12 phrases; no long dense recording exists.

### hard set
24 class and stream lines with 80 key words, spoken by two hosted stock voices, clean and "hard" (15% faster, room
echo, noise 10 dB under the voice). Made speech, not a real teacher (SPEC section 21).

## Infrastructure

### mps
CUDA Multi-Process Service on the A100: lets the three IndicF5 processes run at once (3 lines 3.2 s -> 1.1 s, 20 Nov
2026). Never touched by v1 work.

### tunnel
SSH port forwards from the laptop to the VM's loopback ports; one connection per kind of traffic since `9fae6c8`.

### stream watcher
`scripts/v1/stream-watch.ps1`: read-only watcher of every live session on v0 and v1; writes `events.log`, a row
every 20 s and a summary per stream.

### trace
v1's record per Live phrase and Studio line (`V1_TRACE`): which provider did each step, whether a fallback answered;
JSONL and Prometheus; read by `/metrics-ui`.

### flags
`V1_*` settings in v1's `backend/.env`, all off by default; every new v1 behaviour is behind one ([ARCHITECTURE.md](ARCHITECTURE.md#flags)).

## Versions and process

### v0
The product people use: branch `main`, tag `v0-baseline` (`80c36d8`), ports 3000/8010.

### v1
Built beside v0 on 23 Nov 2026 on branch `v1` (ports 3100/8110), every change behind a flag.

### v1.1
Workstreams WS0-WS6 on 24-25 Nov 2026, closed by `e4944fd`.

### ws0-ws6
v1.1 workstreams: WS0 never die (breaker, ladder), WS1 dense speech (budget, controller, native speed), WS2 session
start and English voice, WS3 Studio HQ toward 96%, WS4 pitch kit, WS5 GPU upgrades prepared, WS6 cleanup.

### needs_approval
`docs/v1/NEEDS_APPROVAL.md`: the ordered 26-item checklist of what waits for the founder or the GPU machine. Items
are cited by number (item 16 = laptop sleep).
