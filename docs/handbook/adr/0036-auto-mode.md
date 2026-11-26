# ADR-0036: Auto mode: the mode decides, nobody manages switches

- **Status:** accepted (measured in v1.2 Part 3: as shipped it is worse than v1.1's best Live setting on the dense reel; three decisions wait for the founder)
- **Date:** 2026-11-26
- **Superseded by:** —

## Context

v1 and v1.1 put every new behaviour behind a flag whose default was off ([ADR-0020](0020-flags-default-off.md)).
By 26 Nov 2026 there were 26 flags and a page of recommendations on which to switch on
(`../../v1/RUNBOOK.md` section 3, v1.1 WS6). The founder's decision of 26 Nov 2026 (v1.2 Part 2): the user never
manages switches. One setting, `V1_MODE=auto`, is v1's default; a list of behaviours is always on; the Live budget
applies by itself when it is needed; the English voice is chosen by a measurement; a line a voice refuses is spoken
by another voice; two guards are always on; what is left of the flags becomes emergency off-switches in one file.

Three earlier findings shaped the parts:

- The budget is one switch for every language, and it trades content for timing: on the dense reel 15-18% fewer
  letters were said, and of 20 Tamil lines read 7 had lost something that mattered (Punjabi 2)
  ([ADR-0028](0028-dub-duration-budget.md), [EXP-024](../experiments/EXP-024-dense-speech-budget.md); read by the author, not a native speaker).
- The one English voice was chosen by a fixed rule that was wrong on a night when the hosted stock voice refused
  lines ([ADR-0031](0031-english-single-voice.md)).
- A line the hosted streamed voice refused had no second ask and no record: it was simply without sound
  (`../../v1/PROGRESS.md` v1.1 WS2, "Found on the way"; `../INCIDENTS.md`).

## Options considered

| Option | What it is | Why it won or lost |
|---|---|---|
| Keep the flags, write better recommendations | as v1.1 | rejected by the founder's decision: the user is not to manage switches |
| Change every flag's default to on | no mode | rejected: no deterministic "as before" left for a baseline, the comparison backends and the tests |
| **One setting with two values, one function that answers for every feature** | `V1_MODE=auto` or `manual`; `app/v1/mode.py` `on(feature)` | **chosen** |
| Settings rewritten at load (auto overwrites the flag fields) | no call sites change | not chosen: a reader of `settings.v1_x` could not tell a decision from a leftover; one function is the rule asked for |
| Overrides as env names | `V1_OFF_TRACE=1` and so on | not chosen: the task names one file, and a file can be read, commented and diffed |
| Budget: always on (v1.1's best timing) | every phrase budgeted | not chosen: normal speech would lose content for nothing |
| **Budget: on only while behind or dense, per language, with two thresholds; loosened by a meaning check** | below | **chosen**; measured in Part 3: on the dense reel it is on for 93-96% of lines |
| Meaning check on every line, before it is spoken | blocking | rejected: it would add a model call to every phrase's path |
| **Meaning check on a sample, after the line was spoken** | below | **chosen** |
| English voice: a fixed rule (v1.1) | `auto` = stock | replaced: the copy is tried at the start and timed |
| Refused line: one more ask in the same voice only (v1.1, English only) | | kept as the first step; then the other voices |

## Decision

**The resolver.** `backend/app/v1/mode.py`: `on(feature, settings)` is the single answer to "is this in force".
In `auto` (the default) the table `AUTO` in that file decides and the per-feature `V1_*` names are not read; an
entry in `backend/config/overrides.yaml` switches one behaviour off (or pins a value). In `manual` every feature
follows its own setting, as before v1.2, and what v1.2 added is off: that is the baseline for measurements, the
comparison backends (`scripts/v1/ab-server.*`, `-Mode`) and the test suite (`tests/conftest.py` pins it). The rule
"HQ never runs without the review" lives in the same function. The overrides file is read once; a file that is
missing, unreadable or wrong in part is logged and ignored and never stops the backend. No page for users lists a
switch; `GET /api/v1/flags` stays as a diagnostic.

**Always on in auto:** the trace, the router, the API log, the breakers and the ladder, stock voices for a `/live`
session without a streamer profile, Studio HQ with its review, the 1.15x fit limit, adaptive takes, the normaliser,
a job's own glossary; also the HQ judge (the reports recommend it with HQ), recordings when a session asks for one,
and the two tool pages. Not part of auto (off; an override may pin them on for a trial): the batching voice server,
Maya, the late-line shortener, the live back-check.

**Auto budget** (`app/v1/dense.py` `AutoGate`, `WordRate`; `LivePipeline._translate`). Per language the budget is
on while one of three holds, each with a higher threshold to start and a lower one to stop: the dub's backlog
(running mean over the language's last lines) over `V1_AUTO_BEHIND_ON_MS` 500 / under `..._OFF_MS` 200; its dubbed
length over the slot (running mean) over `V1_AUTO_RATIO_ON` 1.15 / under `..._OFF` 1.05; speech is dense (speaking
share of the last 30 s over 70% / under 60%, or source words a second over `V1_AUTO_WPS_ON` 4.0 / under 3.2). It
goes off only after `V1_AUTO_CALM_LINES` 4 lines in a row without a reason and not before `V1_AUTO_MIN_ON_MS` 15 s.
While off the translator gets the full prompt: no word limit and no "be brief" (v0's own word limit is not used
either). While on, the budget is v1.1's, scaled by the controller of v1.1 (which now exists only here) and capped
at 0.9 while dense. The dense speed-up limit is 1.3x, not v1.1's 1.4x, which nobody has heard.

**Meaning check** (`app/v1/meaning.py`, `app/v1/guards.py`, `dense.MeaningRate`). Every third spoken line of a
language while its budget is on (every eighth while it is off) is put in a queue of six; one worker asks a language
model, after the line was spoken, whether the dub lost something that matters or says something different. The
judge is the hosted model when one is configured, else the session's translator (`providers.get_judge`); it is a
model call and does not use the hosted voice account's one request. Over 25% lost on the last 6 to 12 judged
budgeted lines: that language's budget gets 0.1 more of the slot (one step); at three steps the language is
translated in full. At or under 10% on six new lines, with the dub behind, and 120 s after the last step: one step
back. Every verdict, the rate with it and every step go to the trace and the session's metrics.

**English voice** (`app/v1/warm.py` `en_choice`, `LivePipeline._en_probe`). In every session with English among the
targets: a voice pinned in the overrides file; else the stock voice when the session has no copied voice at its
start; else one probe line in the copy, timed. The copy is chosen when the probe was there within the viewers' hold
less `V1_EN_PIPELINE_MS` 3800 (the phrase and its text), the stock voice when it took longer, failed, or did not
answer in `V1_EN_PROBE_TIMEOUT_S` 6 s. The first English lines wait for the choice. It is stored on the session and
never changed; the ladder may still give a single line to another voice on failure, and logs it.

**A refused line** (`app/v1/voicechain.py`: the one order `gpu, copy, stock, stock_alt`). A hosted stock voice that
refuses before any sound is asked once more; then every other voice the line can have is asked in that order; only
when none makes it is the line marked `unspoken`, on the phrase, in the trace, in the session's metrics and the
log. Studio the same, per line, and a job finishes with such a line marked instead of failing.

**Guards** (`app/v1/guards.py`, `app/v1/lineguard.py`). Script: every translated line, Live and Studio, and the
transcript where the source language is pinned; a failing line is translated once more, then flagged. Content
shift: Studio judges every line before the voice (and a line shortened to fit once more), translates a failing
one once more, flags it if it fails again; Live counts it on the same sample the meaning check judges and makes
nothing again. Each has its own columns in `eval/live_replay.py`, `eval/v1/studio_table.py` and
`logs/sessions/index.csv`.

## Measured (v1.2 Part 3, 26 Nov 2026)

Live, the dense reel 8 times, Punjabi + Tamil, hold fixed at 6 s, 5 runs a setting taken in turn
([EXP-031](../experiments/EXP-031-auto-mode-dense-reel.md)); mean (lowest-highest):

| | Manual, `V1_LIVE_BUDGET=true` (v1.1's best) | Auto, as shipped | Auto, `live_stock_default: off` | Auto, that and `breaker: off`, `live_degrade: off` |
|---|---|---|---|---|
| Within 0.25 s | 79.1% (73.2-81.8) | 66.3% (57.4-75.1) | 69.6% (55.7-80.8) | 74.2% (72.4-76.6) |
| Within 1 s | 90.0% (87.4-94.0) | 82.4% (71.0-89.3) | 83.9% (72.1-90.9) | 88.5% (86.4-90.1) |
| dur_ratio p90 | 1.16 | 1.20 | 1.15 | 1.16 |
| Skips per 10 min | 3.0 (0-6.1) | 34.1 (0-113.8) | 22.1 (3.0-86.6) | 5.4 (0-11.9) |
| First audio p50 | 2675 ms | 2980 ms | 2965 ms | 2767 ms |
| Lines in the copied voice | 95.1% | 0% | 83.1% (50.9-97.3) | 97.0% |

**Auto mode as shipped is worse than v1.1's best setting on this material.** Three causes, each shown in EXP-031:
stock voices on `/live` queue on the hosted account's one request (the largest); the breakers take the copied
voice away for about 34 s when one health answer takes over 2 s or one line over 4 s (13 times in 3 of 5 runs, the
engine itself never over 0.62 s); the meaning check loosens a language in 16 of 17 sessions, often on 6 judged lines, and a loosened
language runs longer. With the first two switched off, auto is within 5 points of "budget on" within 0.25 s and
overlaps it within 1 s.

- **The auto budget came on in every session and never went off** (93-96% of lines under it): the reel is dense
  throughout. Its other half, the full translation on normal speech, was not exercised.
- **The meaning check:** 14.8-23.3% of sampled budgeted lines judged as lost (about 50-58 judged a run); 1.6-3.2
  loosening steps a run, 0.2-0.4 steps back. Read by eye on 20 lines a language (a non-native reader, as in
  EXP-024), auto did not lose less than "budget on": Tamil 6-10 of 20 against 7, Punjabi 3-9 against 4.
- **A refused line:** no line was without sound and without a mark in 24 sessions; one line was marked unspoken
  (not translated, during a stall of the laptop's connection); 24 lines were spoken by the stock voice after our
  engine's turn failed (22 of them with the breakers on).
- **Script guard:** 77 of about 2830 Live lines failed (72 Tamil), and the second translation put 7 right; the
  rest were spoken and flagged. Studio: 0 of 76.
- **Words heard back** (40 lines a cell): Punjabi 86.4-88.9% and Tamil 83.5-87.1% in the auto settings against
  91.3% and 86.3% with "budget on"; inside what two runs differ by.

Studio HQ in auto mode, the three test videos, one job each ([EXP-032](../experiments/EXP-032-auto-mode-studio.md)):
95.6% of words heard back (94.6-96.5) against 95.9% and 94.5% for v1.1's two HQ settings on another day; 152 s a
video against 129 s and 133 s; 20 of 76 lines flagged, all by the heard-back judge; both guards checked 76 lines
and found nothing; no damaged transcript line.

Not measured: English (the probe and the one voice), a streamer profile, the hosted engine, normal-paced speech,
auto mode with a hold that may grow.

## Consequences

### Good

- One place to read what the product does (`app/v1/mode.py`), one file to switch one behaviour off, and a mode that
  still behaves as before for baselines and tests.
- A line is never without sound without a record; the reason is on the phrase.
- Tests (`backend/tests/test_v1_auto.py`, 41): the resolver and the overrides file (good, bad, missing, unknown
  names), the gate's hysteresis, the meaning rate, the budget on and off in a session, a slow judge that holds
  nothing up, the English choice made once, the fallback order with refusing fake providers, both guards, the old
  env names ignored.

### Bad

- **Measured, and worse than v1.1's best Live setting** (section "Measured"): 66.3% against 79.1% within 0.25 s,
  82.4% against 90.0% within 1 s, 34 against 3 skips per 10 minutes. Every threshold of the auto budget, the
  meaning check and the English probe is still its first value: none was changed after the measurement.
- **The breakers and the ladder were built for a link that is gone; on a link that hiccups they cost more than
  they save.** One health answer over 2 s or one line over 4 s means about 34 s without the copied voice
  (EXP-031). They had never been measured without a stall before v1.2.
- **The meaning check's first step fires on little evidence** (2 lost of 6 judged lines, against a judge that
  calls about 1 line in 6 lost before any loosening), so nearly every session is loosened.
- **The script guard's second translation rarely helps** (7 of 77 Live lines): a Hindi word left in Devanagari in
  a Tamil line is reported, spoken as it is and flagged.
- **Studio HQ takes about 19 s longer a video** than v1.1's HQ with all flags (EXP-032), 6 s of it the
  content-shift judge, which is the model that had just reviewed the same lines and found nothing.
- **`LIVE_STOCK_DEFAULT` always on changes `/live`:** a session without a streamer profile never learns the voice
  on the stream; its consent tick has no effect. Every v1.1 Live number was measured with the learned voice, and the
  only stock-voice runs (two languages, three runs, v1 flags off) had first audio p50 5.1 s and 58.3% within 1 s
  against 2.34 s and 83.3% with the learned voice (`../../v1/RUNBOOK.md` section 3, point 2). Stock voices share the
  hosted account's one request at a time. **Measured in Part 3: this is the largest reason auto is worse.** A line
  in a stock voice started within 1 s 48-83% of the time, a line in the copied voice 87-91%; pure auto ranged
  from 38 skipped lines in a run to 1 with the hosted voice's speed that hour. The way back is one line,
  `live_stock_default: off` (`../../v1/NEEDS_APPROVAL.md` item 29).
- The meaning judge is a model, judging a sample: it can be wrong both ways, and in a hosted-engine session it is of
  the same family as the translator. It costs one hosted model call per batch of up to four judged lines.
- A language whose budget is loosened runs longer than its slot again: the timing the budget bought is given back
  for that language.
- The English probe is one line, once: a service that is slow for that one call decides the whole session. The
  first English lines wait for it (at most the probe's timeout).
- The fallback speaks a line in another voice than the session's: one voice per session is not kept on a failure.
- The script guard sees letters, not words: a Hindi word written in the target's letters passes.
- The API log and the trace are now always written; what they cost per request was never measured
  (`../../v1/RUNBOOK.md`).

## Evidence

- Experiments: [EXP-031](../experiments/EXP-031-auto-mode-dense-reel.md) (auto against "budget on", dense reel),
  [EXP-032](../experiments/EXP-032-auto-mode-studio.md) (three Studio videos).
  Background: [EXP-024](../experiments/EXP-024-dense-speech-budget.md), [EXP-026](../experiments/EXP-026-english-voice-mix.md)
- Commits: see `../history/` (v1.2 Part 2, Parts 3-4)
- Sources: [`PROGRESS.md`](../../v1/PROGRESS.md) "v1.2 Part 2" and "v1.2 Parts 3-4"; [`RUNBOOK.md`](../../v1/RUNBOOK.md) section 3;
  [`NEEDS_APPROVAL.md`](../../v1/NEEDS_APPROVAL.md) item 29; [ADR-0020](0020-flags-default-off.md), [ADR-0027](0027-breakers-degrade-ladder.md),
  [ADR-0028](0028-dub-duration-budget.md), [ADR-0031](0031-english-single-voice.md),
  [ADR-0037](0037-removed-dead-features.md)
