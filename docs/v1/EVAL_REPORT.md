# v1 eval report

Measured on 23 Nov 2026 (early morning, India time) on the dev laptop: v1 backends on 127.0.0.1, the shared GPU
servers of v0 through the existing forwards, the hosted services with the keys v0 uses. Every number here was
measured in these runs; where something was not measured it says so. Raw results are kept in the v1 data folder
(`eval/`), not in the repository.

**Read this first**

- "v0" in the tables is **v1 with every flag off**. Router tests show that this builds the same providers as v0's
  fixed table, and it is the same pipeline code. v0 itself (port 8010) was only asked for its health: a test
  session on it would be a session in the product people use, and that was not ours to start.
- Runs are few: three per Live setup, one per Studio video. v0's own notes found that two equal Live runs differ
  by about 10 points in timing and 6 in words heard back. Ranges are given so that this is visible.
- The backend ran on the laptop, so every phrase crossed the laptop-to-VM link several times. v0 measured first
  audio p50 of 1.8 s with the backend on the GPU machine and 2.3 s through the link; only the second was possible
  here.
- The speech in the test material is made by hosted stock voices or is one dense 24.9 s reel. No person at a
  microphone, no real stream, no listener's ear.

## Targets

| Target | Measured here | Reached? |
|---|---|---|
| Studio: words heard back at least 96% | HQ 92.5% (91.1-93.5 over three videos); standard 89.2% (84.9-93.4). **Corrected on 25 Nov (section 6): the counting rule was taking points off Bengali; the same output is 95.5% and 91.1% by the corrected rule, and a rerun gave 95.9% and 90.6%** | no (95.9%; and see section 6 on what the figure does not see) |
| Studio: speed-up at most 1.15x | HQ largest 1.15x with the limit on (1.02x, 1.06x, 1.15x); standard 1.05x at most on these videos | yes, on videos that hardly needed it |
| Live: first audio p50 at most 1.8 s | 2.3-2.5 s through the link | no (not measurable here without the link) |
| Live: on time at least 90% | 56-70% within 0.25 s, 76-83% within 1 s | no |
| Live: key words on hard audio at least 73 of 80 | hosted 71.3 (71-72); our Whisper 52 (50-55) | 1-2 words short, see section 3 |
| After a VM restart, warm and green in 5 minutes | not tested (no VM restart was ours to do) | not measured |

## 1. Live (dense reel, GPU engine, Tamil + Bengali, sync mode, hold 6 s)

`python -m eval.v1.live`: the same recording through each backend in turn, never two at once. Mean of 3 runs
(range).

### 1.1 Voice learned from the stream, three loops a run

| | flags off ("v0") | `V1_PHRASE_DYNAMIC` | dynamic + ahead + prefix + late-shorten + 1.2x cap |
|---|---|---|---|
| First audio p50 | 2.34 s (2.27-2.40) | 2.37 s (2.28-2.41) | 2.46 s (2.42-2.50) |
| First audio p95 | 6.6 s (6.0-7.7) | 6.8 s (5.7-8.0) | 9.1 s (6.3-11.0) |
| Heard p50 (when a viewer hears it) | 5.5 s (4.8-5.8) | 4.3 s (4.1-4.4) | 5.2 s (4.7-5.6) |
| Within 0.25 s of the video moment | 69.6% (68.8-70.1) | 64.5% (62.7-66.0) | 56.0% (52.4-59.6) |
| Within 1 s | 83.3% (81.2-85.0) | 79.8% (78.9-81.4) | 75.6% (68.3-79.7) |
| Lateness p95 | 2.9 s (2.6-3.1) | 3.1 s (2.9-3.3) | 3.2 s (3.1-3.3) |
| Hold at the end of the run | 6.7 s (6-7) | 6.0 s (6-6) | 6.7 s (6-7) |
| Phrases a run | 36.7 | 32 | 33.3 |
| Skipped as too late | 4.7 (3-6) | 4 (1-6) | 1.7 (0-3) |
| At the speed limit | 20 | 18 (16-21) | 25.3 (21-28) |
| In the copied voice | 93.8% | 91.7% | 92.8% |
| Translation p50 | 539 ms | 549 ms | 553 ms |
| First word of the session to first audio | 7.2 s (6.4-8.0) | 7.2 s (6.3-7.8) | 7.6 s (6.4-8.7) |
| Lines said shorter instead of skipped | - | - | 2 (1-3) |
| Translations started ahead / used | - | - | 4.7 / 0 |
| Fallback (translation, voice) | 0%, 0% | 0%, 0.5% | 0%, 0% |

### 1.2 Stock voices (a voice is ready from the first word), two loops a run

| | flags off | `V1_PHRASE_DYNAMIC` |
|---|---|---|
| First word of the session to first audio | 5.9 s (4.9-6.5) | 4.1 s (4.0-4.4) |
| First audio p50 | 5.1 s (2.6-6.6) | 5.2 s (2.7-6.6) |
| Within 1 s of the moment | 58.3% (45.5-81.6) | 56.9% (43.5-81.6) |
| Hold at the end of the run | 8.7 s (6-10) | 9.3 s (7-11) |

Stock voices in two languages go through the hosted account one request at a time, which is why these runs are
slower and spread wider than the copied-voice runs above.

### 1.3 What each Live flag did

| Flag | Measured effect | Verdict |
|---|---|---|
| `V1_PHRASE_DYNAMIC` | first audio of a session 1.7 s earlier when a voice is ready at the start; no gain when the voice is learned from the stream (it waits about 7 s for the voice); 5 points fewer phrases on time from the longer later phrases; the short-line merge was not exercised (this reel has no one- or two-word lines) | useful for the opening of a streamer session; costs timing on dense speech |
| `V1_SPEC_TRANSLATE` | 4-6 early translations started a run, none used, in 5 runs | no gain with partials about 470 ms apart; removed in v1.1 WS6 |
| `V1_LLM_PREFIX_CACHE` | 61.4% of prompt tokens from the server's cache with it off and with it on (40 calls each); call p50 379 ms against 420 ms | no gain: the cache was already on and already held each prompt; removed in v1.1 WS6 |
| `V1_LIVE_LATE_SHORTEN` | 1-3 lines a run said shorter; skips 4.7 -> 1.7 a run (inside a bundle whose timing was worse) | does what it says; its own effect on timing not separated |
| `LIVE_FIT_MAX_TEMPO=1.2` | phrases at the limit 20 -> 25 | as expected; whether 1.2x sounds better than 1.3x needs ears |
| `V1_LIVE_BACKCHECK` | not measured: no scorer without the QA server | waits for `NEEDS_APPROVAL.md` item 6 |
| `V1_LIVE_STOCK_DEFAULT` | not a timing change; covered by a test | a product decision |
| `V1_ROUTER` | one run with it on: same providers in the trace, first audio 2.4 s, 74% / 85% (0.25 s / 1 s); inside the run-to-run spread of the runs with it off | safe to switch on |
| `V1_TRACE` | every run above was traced; no error from it | safe to switch on |

Not measured for Live: words heard back per run, a person at a microphone, a stream with short lines, a second
viewer language pair, the backend on the GPU machine.

## 2. Studio (GPU engine, voice copied from the video with consent, Tamil + Bengali)

`python -m eval.v1.studio`: each video once through "standard" (flags off) and once through HQ
(`V1_STUDIO_HQ`, `V1_FIT_115`, router on). Afterwards every dubbed line, as it is in the video, is heard back by
the same scorer (the hosted speech-to-text) for both. Three videos of twelve spoken lines each, made from the hard
set's speech (`eval/v1/make_video.py`): 24, 26 and 26 dubbed lines a job.

| Video | Standard: words heard back | HQ: words heard back | Standard: time | HQ: time | HQ takes | HQ flagged | Largest speed-up (standard / HQ) |
|---|---|---|---|---|---|---|---|
| A (lines 1-12) | 93.4% | 92.9% | 84 s | 222 s | 54 | 8 of 24 | 1.00x / 1.02x |
| B (lines 13-24) | 84.9% | 93.5% | 78 s | 312 s | 62 | 8 of 26 | 1.00x / 1.06x |
| C (lines 7-18, shorter pauses) | 89.3% | 91.1% | 84 s | 232 s | 63 | 9 of 26 | 1.05x / 1.15x |
| **Mean (range)** | **89.2% (84.9-93.4)** | **92.5% (91.1-93.5)** | 82 s | 255 s | 60 | 25 of 76 | |

By language: standard Tamil 93.9 / 87.1 / 88.2%, Bengali 93.0 / 82.8 / 90.4%; HQ Tamil 95.8 / 97.4 / 90.2%,
Bengali 90.1 / 89.6 / 92.1%.

Inside the HQ jobs, the first take of a line against the take that was kept:

| Video | Tamil: first -> kept | Bengali: first -> kept | Lines that needed more than one take |
|---|---|---|---|
| A | 85.0% -> 95.8% | 87.7% -> 90.1% | 13 of 24 |
| B | 91.2% -> 97.4% | 83.4% -> 89.6% | 17 of 26 |
| C | 92.4% -> 94.1% | 87.8% -> 92.1% | 18 of 26 |

These are the scores the job itself gave its takes before fitting. The first table hears the finished line, after
any speed-up, so the two differ a little (video C, Tamil: kept takes 94.1%, finished lines 90.2%, with lines sped
up to 1.15x).

The dense one-line reel: standard 41 s and 88.2%, HQ 92 s and 87.7%; no speed-up needed in either.

What this says:

- **HQ is 3.3 points better on average and much steadier** (its worst video is 91.1%, standard's is 84.9%), for
  about three times the time. It is not at 96%.
- **Picking among takes is where the gain comes from:** the kept take beats the first take by 2 to 11 points.
- **About a third of the lines are flagged** at the 90% line. Several have the same score on every take, which
  points at the wording or the scorer (a subject term the speech-to-text writes differently), not at the voice.
  The flag count is only useful once a person has listened to a sample of them; that was not done.
- **One fault found and fixed:** in one HQ job our voice engine dropped one request on the first Bengali line; the
  hosted copy of the voice answered, and because a job keeps the voice that spoke first, all 13 Bengali lines of
  that job went to the hosted copy. The job's own voice is now tried twice before another one answers. That job
  was not made again (its takes are in the cache), so 13 of the 76 HQ lines above are in the hosted copy.
- **The scorer was corrected once during this work:** it counted an abbreviation said as separate letters as
  words not heard. With the first rule video A read 91.3% (standard) and 90.9% (HQ); the table uses the corrected
  rule for both paths.
- **Not measured:** speaker similarity (needs the QA server; and the model used for earlier figures is
  non-commercial), more than one run a video (a second run is served from the cache), a video with two speakers,
  music under the voice (ducking and loudness ran but nobody listened), the big translation model, Maya 2.

## 3. Speech-to-text on the hard set

`python -m eval.v1.stt`: 24 lines, 80 key words; clean once, hard three times (15% faster, echo, noise 10 dB
under the voice; new noise each run).

| Provider | Clean | Hard, mean of 3 (range) |
|---|---|---|
| Hosted (Prisma) | 77 of 80 | 71.3 of 80 (71-72) |
| Our Whisper (9030) | 70 of 80 | 52 of 80 (50-55) |
| Indic Transcribe | not configured (not loaded) | not configured |

v0's earlier single run read 73 and 49 on hard audio; this harness makes the hard version with its own noise, so
the two are close, not identical. The order of the two providers in the GPU engine (hosted first) stands.

## 4. Other measurements

- **Status endpoint:** the six shared servers answer in 0.4-0.7 s each through the link, asked at the same time.
- **Warm-up** (`scripts/v1/warmup.sh`, one run): translation 0.8 s, hosted stock voice 1.9 s, three voice
  engines 1.4 s, our speech-to-text 1.0 s, separation 1.3 s.
- **Translation server** (read from it): vLLM 0.34.0, prefix caching on, 52.8% of all prompt tokens since its
  start served from the cache.
- **Tests:** 159 pass, 1 skipped (the Postgres store, which needs a database).

## 5. How to repeat

```bash
scripts/v1/ab-server.sh 8111 base                      # flags off
scripts/v1/run-local.sh                                # the v1 backend with the flags under test
python -m eval.v1.make_video --set <data>/eval/stt_set --out <data>/eval/class12.mp4
scripts/v1/eval-all.sh <data>/eval <data>/eval/out     # Live, Studio and speech-to-text, one at a time
```

`eval-all.sh` does not run against v0 unless `V0` is set to its address.

Section 6: the comparison backends named at the head of `scripts/v1/eval-studio-ws3.sh` (start them with
`scripts\v1\ab-server.ps1`), then

```bash
scripts/v1/eval-studio-ws3.sh <data>/eval <data>/eval/ws3/run1
python -m eval.v1.studio_table <data>/eval/ws3/run1 --ab <data>/ab                      # the tables
python -m eval.v1.rescore --data <data> --jobs <ids of old jobs> --out <dir>            # old output, new rule
```

## 6. Studio HQ again, with the corrected judge (v1.1 WS3, 25 Nov 2026)

One job per video and setup, 25 Nov 2026 01:48-02:45 IST, the three videos of section 2, Tamil + Bengali, GPU
engine, the voice copied from the video with consent, one job at a time, no stream live. Full account, the flags
and the mistakes made on the way: `PROGRESS.md`, "v1.1 WS3".

**Read this first**

- **Section 2's figures are by a counting rule that was wrong for Bengali.** One Bengali letter can be stored in
  two ways; the translation model writes one, the speech-to-text the other, and they were counted as different
  words. A line heard back word for word scored 86%. The judge itself (the hosted speech-to-text) is the same
  then and now. Figures by the old and the new rule are not comparable; the 23 Nov output was scored again by the
  new rule from the hearings stored that day, without making a voice line, and that column is.
- **Words heard back does not say that the dub says what the speaker said.** It compares the dub with its own
  text. In two of the three HQ jobs, on 23 Nov and again today with the new flags off, v1's "merge the hearings"
  and "clean" steps had changed the transcript: in video C twelve of thirteen lines hold the line before them, in
  video B all thirteen came back in Latin letters and three lost their first words. Those jobs score 93.3% and
  98.1%. With `V1_HQ_REVIEW` such lines are put back as first heard.
- One job per video. Two equal jobs differ by more than most of the differences below (the standard pipeline's
  Tamil on video A: 93.9% on 23 Nov, 82.9% today).

### 6.1 Before and after

| | 23 Nov, as reported (old rule) | 23 Nov output, new rule | 25 Nov rerun, new rule |
|---|---|---|---|
| Standard, words heard back | 89.2% (84.9-93.4) | 91.1% (87.3-95.3) | 90.6% (88.4-93.0) |
| HQ, words heard back | 92.5% (91.1-93.5) | 95.5% (93.9-96.7) | 95.9% (93.3-98.1) |
| HQ Tamil, video A / B / C | 95.8 / 97.4 / 90.2 | 95.8 / 97.4 / 90.2 | 96.6 / 97.8 / 87.5 |
| HQ Bengali, video A / B / C | 90.1 / 89.6 / 92.1 | 96.1 / 95.9 / 97.7 | 95.9 / 98.4 / 99.2 |
| HQ lines flagged, of 76 | 25 | 15 | 15 |
| HQ takes made | 179 | 179 (the same takes) | 143 |
| HQ total time, video A / B / C | 222 / 312 / 232 s | the same jobs | 133 / 117 / 136 s |
| Standard total time, video A / B / C | 84 / 78 / 84 s | the same jobs | 81 / 54 / 66 s |

Scored again: all 179 takes of the three 23 Nov HQ jobs and all 152 finished lines of the six jobs (the HQ
jobs' folders had expired; their finished lines were made again from the kept take and its slot; one of the 152
was not in the score cache and was heard again). HQ had been at 95.5% on 23 Nov, not 92.5%.

### 6.2 The rerun, per video and language (corrected rule; every line judged by the hosted speech-to-text)

Standard = every flag off. HQ = `V1_STUDIO_HQ`, `V1_FIT_115`, `V1_ROUTER` as in section 2, with `V1_HQ_JUDGE`.
All flags = HQ + `V1_HQ_ADAPTIVE`, `V1_HQ_NORMALISE`, `V1_HQ_AUTO_GLOSSARY`, `V1_HQ_REVIEW`.

| Video | Language | Standard: heard back | HQ: heard back / takes / flagged | All flags: heard back / takes / flagged |
|---|---|---|---|---|
| A | Tamil | 82.9% | 96.6% / 23 / 3 of 12 | 90.7% / 33 / 5 of 12 |
| A | Bengali | 94.0% | 95.9% / 22 / 2 of 12 | 95.7% / 20 / 3 of 12 |
| B | Tamil | 95.5% | 97.8% / 22 / 2 of 13 | 94.3% / 27 / 5 of 13 |
| B | Bengali | 85.4% | 98.4% / 23 / 1 of 13 | 93.5% / 25 / 4 of 13 |
| C | Tamil | 90.7% | 87.5% / 36 / 6 of 13 | 96.2% / 32 / 2 of 13 |
| C | Bengali | 95.2% | 99.2% / 17 / 1 of 13 | 96.8% / 19 / 2 of 13 |
| **Mean of the three videos (lowest-highest)** | | **90.6% (88.4-93.0)** | **95.9% (93.3-98.1)**, 143 takes, 15 of 76 flagged | **94.5% (93.2-96.5)**, 156 takes, 21 of 76 flagged |
| Total time, video A / B / C | | 81 / 54 / 66 s | 133 / 117 / 136 s | 140 / 129 / 130 s |
| Transcript lines that are not the line first heard, A / B / C | | does not merge | 0 / 13 / 12 | 0 / 0 / 0 |

A standard job makes one take a line (76) and flags nothing: it does not score its lines.

**Target, 96% of words heard back: not reached.** HQ 95.9% (two videos of three over 96%), and two of its three
dubs are of a damaged transcript. All flags 94.5% (one video of three over 96%), with the transcripts intact.

The all-flags jobs score lower than HQ on videos A and B, in a first build of the flags too (94.8% over the three
videos, 93.0-95.8). Read line by line, most of their flagged lines are a spelling the judge writes differently for
the same sound (Bengali নিচে / নীচে, হলো / হল; Tamil ஐந்நூறு / ஐநூறு, யாரு / யார்) and English terms written in
the other script, which the review keeps and the plain translation drops or replaces. Nobody has listened to
them; that is what `/studio/calibrate` is for (`CALIBRATION.md`: no labels yet).

### 6.3 Adaptive takes against fixed takes (same transcript and translation in both)

| | Fixed: 5 takes of every line | Adaptive: 1 take, more only under 90%, at most 5 | |
|---|---|---|---|
| Voice stage, video A / B / C | 170 / 176 / 178 s | 62 / 66 / 79 s | 64 / 62 / 56% less; 61% over the three |
| Takes | 380 | 143 | |
| Words heard back, finished lines | 96.1% (92.3-99.1) | 95.0% (93.2-97.8) | separate jobs, separate takes |
| The rule applied to the fixed jobs' own 380 takes | best of five: 96.8% | 145 takes, the same take kept on all 76 lines: 96.8% | no change, 62% fewer takes |
| ... with the same-words stop (as the adaptive jobs ran; off by default now) | | 129 takes, 96.3%, a lower-scored take kept on 3 of 76 lines | |

Against v1's own rule (up to four takes until one passes) adaptive made the same number of takes (143 and 143).
The first take alone scores 93.8% on those 380 takes; picking among takes is still where HQ's gain is.

### 6.4 The text flags

- **Review** (`V1_HQ_REVIEW`): 76 lines read, 24 edited (12 numbers and names, 9 meaning, 2 register, 1 length),
  none refused; a wrong number, a misspelt place name, a verb that changed the meaning among them. Read from the
  reviewer's notes, not confirmed by a speaker of either language.
- **Transcript guard** (same flag): video C 12 lines merged, 8 put back; none of the 38 lines of the three
  all-flags jobs fails the rule that 25 of the 38 lines of the HQ jobs fail.
- **Auto-glossary** (`V1_HQ_AUTO_GLOSSARY`): 16 candidates over the three videos; effect not separated.
- **Normaliser** (`V1_HQ_NORMALISE`): changed no line; these videos have no digits or signs. Unit tests only
  (Hindi, Bengali, Tamil, English).

**Not measured:** more than one job per video and setup; a person's ear on any line; speaker similarity; Hindi
as a target language (a second judge exists for it and was tested with fakes only); the judge's fallback in a
real job (the hosted judge answered every one of its 1617 hearings: 1137 takes, 480 finished lines); the normaliser on a video with digits; music under the
voice; a long video.
